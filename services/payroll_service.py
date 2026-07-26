import datetime
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import func
from currency_utils import D, DECIMAL_ZERO
from models import (
    PayrollRun, PayrollRunItem, Employee, Attendance,
    EmployeeWithdrawal, CommissionEntry, TreasuryTransaction, TreasuryAccount,
    JournalEntry, JournalLine, Account,
)


class PayrollService:
    def __init__(self, db: Session, user):
        self.db = db
        self.user = user

    def calc_run_items(self, period_start, period_end) -> list:
        items = []
        employees = self.db.query(Employee).order_by(Employee.name).all()
        for emp in employees:
            sal = D(emp.salary)
            days_in_month = (period_end - period_start).days + 1
            daily_rate = sal / D(days_in_month) if days_in_month else DECIMAL_ZERO

            basic_sal = sal
            housing = D(emp.housing_allowance)
            transport = D(emp.transport_allowance)
            other_allow = D(emp.other_allowances)
            si = D(emp.social_insurance)

            att_records = self.db.query(Attendance).filter(
                Attendance.employee_id == emp.id,
                Attendance.date >= period_start,
                Attendance.date <= period_end,
                Attendance.approved == 1,
            ).all()

            absence_days = sum(1 for a in att_records if a.status == "absent")
            late_mins = sum(a.late_minutes or 0 for a in att_records)
            overtime_hrs = sum(D(a.overtime_hours or 0) for a in att_records)

            abs_ded = D(absence_days) * daily_rate
            late_ded = D(late_mins) / D("60") * daily_rate * D("0.5")
            overtime_amt = overtime_hrs * daily_rate * D("1.5")

            advances = self.db.query(func.coalesce(func.sum(EmployeeWithdrawal.amount), 0)).filter(
                EmployeeWithdrawal.employee_id == emp.id,
                EmployeeWithdrawal.date >= period_start,
                EmployeeWithdrawal.date <= period_end,
                EmployeeWithdrawal.withdrawal_type == "advance",
            ).scalar() or 0
            adv_ded = D(advances)

            commission = self.db.query(func.coalesce(func.sum(CommissionEntry.calculated_amount), 0)).filter(
                CommissionEntry.recipient_id == emp.id,
                CommissionEntry.recipient_type == "employee",
                CommissionEntry.status.in_(["calculated", "earned", "paid"]),
                CommissionEntry.created_at >= datetime.datetime.combine(period_start, datetime.time.min),
                CommissionEntry.created_at <= datetime.datetime.combine(period_end, datetime.time.max),
            ).scalar() or 0
            comm_amt = D(commission)

            gross = basic_sal + housing + transport + other_allow + overtime_amt + comm_amt
            tot_ded = abs_ded + late_ded + adv_ded + si
            net = gross - tot_ded

            items.append(PayrollRunItem(
                employee_id=emp.id,
                basic_salary=basic_sal,
                housing_allowance=housing,
                transport_allowance=transport,
                other_allowances=other_allow,
                overtime_amount=overtime_amt,
                commission_amount=comm_amt,
                absence_deduction=abs_ded,
                late_deduction=late_ded,
                advances_deduction=adv_ded,
                social_insurance=si,
                other_deductions=DECIMAL_ZERO,
                gross_pay=gross,
                total_deductions=tot_ded,
                net_pay=net,
            ))
        return items

    def _ensure_payroll_accounts(self) -> dict:
        expense = self.db.query(Account).filter(Account.code == "5010").first()
        if not expense:
            expense = Account(code="5010", name="مصروف رواتب", account_type="expense")
            self.db.add(expense)
            self.db.flush()
        payable = self.db.query(Account).filter(Account.code == "2010").first()
        if not payable:
            payable = Account(code="2010", name="مستحق رواتب", account_type="liability")
            self.db.add(payable)
            self.db.flush()
        return {"expense": expense.id, "payable": payable.id}

    def create_run(self, name: str, period_start, period_end, notes: str = "") -> PayrollRun:
        existing = self.db.query(PayrollRun).filter(
            PayrollRun.period_start == period_start,
            PayrollRun.period_end == period_end,
        ).first()
        if existing:
            raise ValueError("duplicate")

        run = PayrollRun(
            name=name, period_start=period_start, period_end=period_end,
            status="draft", notes=notes, created_by=self.user.username,
        )
        self.db.add(run)
        self.db.flush()

        calc_items = self.calc_run_items(period_start, period_end)
        total_gross = DECIMAL_ZERO
        total_ded = DECIMAL_ZERO
        total_net = DECIMAL_ZERO
        for item in calc_items:
            item.payroll_run_id = run.id
            self.db.add(item)
            total_gross += item.gross_pay
            total_ded += item.total_deductions
            total_net += item.net_pay
        run.total_gross = total_gross
        run.total_deductions = total_ded
        run.total_net = total_net
        return run

    def update_status(self, run_id: int, status: str):
        run = self.db.query(PayrollRun).get(run_id)
        if not run:
            raise ValueError(f"PayrollRun {run_id} not found")
        now = datetime.datetime.utcnow()
        run.status = status
        uname = getattr(self.user, "username", "system")
        if status == "reviewed":
            run.reviewed_by = uname
            run.reviewed_at = now
        elif status == "approved":
            run.approved_by = uname
            run.approved_at = now
            acc = self._ensure_payroll_accounts()
            from services.accounting_service import AccountingService
            asc = AccountingService(self.db)
            ttl = D(run.total_net)
            if ttl > DECIMAL_ZERO:
                total_gross = D(run.total_gross) or DECIMAL_ZERO
                commission_gross = sum((D(i.commission_amount) for i in run.items), DECIMAL_ZERO)
                # نوزّع صافي الرواتب على "مصروف رواتب" و"مصروف عمولات" بنسبة العمولة
                # من الإجمالي، عشان العمولات متتقيدش غلط كأنها راتب ثابت في قائمة الدخل.
                if total_gross > DECIMAL_ZERO and commission_gross > DECIMAL_ZERO:
                    commission_net = min((commission_gross / total_gross) * ttl, ttl)
                else:
                    commission_net = DECIMAL_ZERO
                salary_net = ttl - commission_net

                lines = []
                if salary_net > DECIMAL_ZERO:
                    lines.append((acc["expense"], salary_net, DECIMAL_ZERO))
                if commission_net > DECIMAL_ZERO:
                    lines.append((asc._acc_id("commissions"), commission_net, DECIMAL_ZERO))
                lines.append((acc["payable"], DECIMAL_ZERO, ttl))
                asc.post(
                    lines=lines,
                    source_type="payroll_run", source_id=run.id,
                    description=f"صرف رواتب {run.name} (أساسي + عمولات)",
                    created_by=uname,
                )
        elif status == "paid":
            run.paid_by = uname
            run.paid_at = now
            ttl = D(run.total_net)
            if ttl > DECIMAL_ZERO:
                treasury = self.db.query(TreasuryAccount).filter(
                    TreasuryAccount.type == "treasury"
                ).first()
                if treasury:
                    from services.treasury_service import TreasuryService
                    ts = TreasuryService(self.db)
                    txn = TreasuryTransaction(
                        account_id=treasury.id, type="out", amount=ttl,
                        description=f"صرف رواتب {run.name}",
                        date=datetime.date.today(),
                    )
                    self.db.add(txn)
                    self.db.flush()
                    run.voucher_txn_id = txn.id
                    ts.deduct_balance(treasury.id, ttl)

                    # نقفل دورة العمولات اللي دخلت في الرواتب دي: تتحول لـ "مدفوعة"
                    # وترتبط بنفس حركة الخزنة، عشان تقارير العمولات المستحقة تبقى صح
                    # (بدل ما تفضل معلّقة على "calculated" للأبد بعد ما بالفعل اتدفعت).
                    entries = self.db.query(CommissionEntry).filter(
                        CommissionEntry.recipient_type == "employee",
                        CommissionEntry.status.in_(["calculated", "earned"]),
                        CommissionEntry.created_at >= datetime.datetime.combine(run.period_start, datetime.time.min),
                        CommissionEntry.created_at <= datetime.datetime.combine(run.period_end, datetime.time.max),
                    ).all()
                    for e in entries:
                        e.status = "paid"
                        e.paid_date = now
                        e.paid_amount = D(e.calculated_amount)
                        e.linked_txn_id = txn.id
        self.db.flush()
