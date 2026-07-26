import datetime
from decimal import Decimal
from sqlalchemy.orm import Session
from models import TreasuryAccount, DefaultTreasuryAccount
from currency_utils import D, DECIMAL_ZERO


class InsufficientBalanceError(ValueError):
    pass

class CurrencyMismatchError(ValueError):
    pass

class AccountNotSelectedError(ValueError):
    pass


class TreasuryService:
    def __init__(self, db: Session):
        self.db = db

    def get_balance(self, account_id: int) -> Decimal:
        account = self.db.query(TreasuryAccount).get(account_id)
        if not account:
            return DECIMAL_ZERO
        return D(account.balance)

    def resolve_account(self, account_id, operation_type, branch="main"):
        if account_id:
            account = self.db.query(TreasuryAccount).get(account_id)
            if account:
                return account
        default = self.db.query(DefaultTreasuryAccount).filter(
            DefaultTreasuryAccount.operation_type == operation_type,
            DefaultTreasuryAccount.branch == branch,
        ).first()
        if default:
            return default.account
        raise AccountNotSelectedError(
            f"لم يتم اختيار حساب {operation_type} يرجى تحديد حساب أو إعداد حساب افتراضي"
        )

    def validate_withdrawal(self, account_id: int, amount, description="withdrawal"):
        d_amount = D(amount)
        if d_amount <= DECIMAL_ZERO:
            return
        account = self.db.query(TreasuryAccount).get(account_id)
        if not account:
            raise ValueError(f"Account #{account_id} not found")
        if account.allow_negative_balance:
            return
        balance = D(account.balance)
        if balance < d_amount:
            raise InsufficientBalanceError(
                f"الرصيد غير كافٍ في {account.name}: الرصيد المتاح {balance:.2f}، المبلغ المطلوب {d_amount:.2f}"
            )

    def validate_currency(self, account_id: int, base_currency_id=None):
        account = self.db.query(TreasuryAccount).get(account_id)
        if not account:
            return
        if account.currency_id and base_currency_id and account.currency_id != base_currency_id:
            from models import Currency
            acc_cur = self.db.query(Currency).get(account.currency_id)
            op_cur = self.db.query(Currency).get(base_currency_id)
            raise CurrencyMismatchError(
                f"عملة الحساب ({acc_cur.code if acc_cur else '?'}) لا تطابق عملة العملية ({op_cur.code if op_cur else '?'})"
            )

    def deduct_balance(self, account_id: int, amount):
        d_amount = D(amount)
        if d_amount <= DECIMAL_ZERO:
            return
        account = self.db.query(TreasuryAccount).get(account_id)
        if account:
            account.balance = D(account.balance) - d_amount

    def add_balance(self, account_id: int, amount):
        d_amount = D(amount)
        if d_amount <= DECIMAL_ZERO:
            return
        account = self.db.query(TreasuryAccount).get(account_id)
        if account:
            account.balance = D(account.balance) + d_amount

    def restore_balance(self, account_id: int, amount):
        d_amount = D(amount)
        if d_amount <= DECIMAL_ZERO:
            return
        account = self.db.query(TreasuryAccount).get(account_id)
        if account:
            account.balance = D(account.balance) + d_amount

    def create_transaction(self, account_id: int, txn_type: str, amount, description: str = "",
                           user=None) -> "TreasuryTransaction":
        from models import TreasuryTransaction
        d_amount = D(amount)
        if d_amount <= DECIMAL_ZERO:
            raise ValueError("Amount must be positive")
        account = self.resolve_account(account_id, "withdrawal" if txn_type == "out" else "collection")
        if txn_type == "out":
            self.validate_withdrawal(account.id, d_amount, description)
        txn = TreasuryTransaction(
            account_id=account.id, type=txn_type, amount=d_amount,
            description=description, date=datetime.date.today(),
            status="draft", created_by=getattr(user, "username", "system") if user else "system",
        )
        self.db.add(txn)
        self.db.flush()
        if txn_type == "out":
            self.deduct_balance(account.id, d_amount)
        else:
            self.add_balance(account.id, d_amount)
        return txn

    def post_expense(self, expense_id: int, user=None):
        from models import Expense, TreasuryTransaction
        e = self.db.query(Expense).get(expense_id)
        if not e:
            raise ValueError(f"Expense {expense_id} not found")
        from services.workflow_service import WorkflowService
        WorkflowService(self.db).post(e, user)
        if not e.account_id:
            account = self.resolve_account(None, "expense")
            e.account_id = account.id
        account = self.db.query(TreasuryAccount).get(e.account_id)
        if account:
            self.validate_withdrawal(account.id, D(e.amount), f"مصروف: {e.category}")
        self.db.add(TreasuryTransaction(
            account_id=e.account_id, type="out", amount=D(e.amount),
            description=f"مصروف: {e.category}", date=datetime.date.today(),
            status="posted", created_by=getattr(user, "username", "system") if user else "system",
        ))
        self.deduct_balance(e.account_id, D(e.amount))
        from services.accounting_service import AccountingService
        AccountingService(self.db).post_expense(e, created_by=getattr(user, "username", "system") if user else "system")
        self.db.flush()

    def create_transfer(self, from_account_id: int, to_account_id: int, amount, fee=DECIMAL_ZERO,
                        exchange_rate=1, description="", user=None) -> "TreasuryTransfer":
        from models import TreasuryTransfer
        if from_account_id == to_account_id:
            raise ValueError("لا يمكن التحويل لنفس الحساب")
        d_amount = D(amount)
        if d_amount <= DECIMAL_ZERO:
            raise ValueError("المبلغ يجب أن يكون أكبر من صفر")
        d_fee = D(fee)
        if d_fee < DECIMAL_ZERO:
            raise ValueError("الرسوم لا يمكن أن تكون سلبية")
        d_rate = D(exchange_rate)
        if d_rate <= DECIMAL_ZERO:
            raise ValueError("سعر الصرف يجب أن يكون أكبر من صفر")
        d_converted = d_amount * d_rate
        if d_converted <= d_fee:
            raise ValueError("المبلغ المحول يجب أن يتجاوز الرسوم")
        d_net = d_converted - d_fee
        self.resolve_account(from_account_id, "withdrawal")
        transfer = TreasuryTransfer(
            from_account_id=from_account_id, to_account_id=to_account_id,
            amount=d_amount, converted_amount=d_converted, exchange_rate=d_rate,
            fee=d_fee, net_amount=d_net,
            description=description, date=datetime.date.today(),
            status="draft", created_by=getattr(user, "username", "system") if user else "system",
        )
        self.db.add(transfer)
        self.db.flush()
        return transfer

    def post_transfer(self, transfer_id: int, user=None):
        from models import TreasuryTransfer, TreasuryTransaction, JournalEntry
        from services.accounting_service import AccountingService
        t = self.db.query(TreasuryTransfer).get(transfer_id)
        if not t:
            raise ValueError(f"Transfer {transfer_id} not found")
        d_amount = D(t.amount)
        d_net = D(t.net_amount)
        d_fee = D(t.fee)
        self.validate_withdrawal(t.from_account_id, d_amount, t.description or "تحويل خزنة")
        from services.workflow_service import WorkflowService
        WorkflowService(self.db).post(t, user)
        self.db.add(TreasuryTransaction(
            account_id=t.from_account_id, type="out", amount=d_amount,
            description=f"تحويل إلى {t.to_account.name} - {t.description or ''}",
            date=datetime.date.today(), status="posted",
            created_by=getattr(user, "username", "system") if user else "system",
        ))
        self.deduct_balance(t.from_account_id, d_amount)
        self.db.add(TreasuryTransaction(
            account_id=t.to_account_id, type="in", amount=d_net,
            description=f"تحويل من {t.from_account.name} - {t.description or ''}",
            date=datetime.date.today(), status="posted",
            created_by=getattr(user, "username", "system") if user else "system",
        ))
        self.add_balance(t.to_account_id, d_net)
        if d_fee > DECIMAL_ZERO:
            self.db.add(TreasuryTransaction(
                account_id=t.from_account_id, type="out", amount=d_fee,
                description=f"رسوم تحويل إلى {t.to_account.name} - {t.description or ''}",
                date=datetime.date.today(), status="posted",
                created_by=getattr(user, "username", "system") if user else "system",
            ))
            self.deduct_balance(t.from_account_id, d_fee)
            asc = AccountingService(self.db)
            asc.post(
                lines=[(asc._acc_id("opex"), d_fee, DECIMAL_ZERO),
                       (asc._acc_id("treasury"), DECIMAL_ZERO, d_fee)],
                source_type="transfer", source_id=t.id,
                description=f"رسوم تحويل #{t.id}: {t.description or ''}",
                created_by=getattr(user, "username", "system") if user else "system",
            )
        self.db.flush()

    def cancel_transfer(self, transfer_id: int, user=None):
        from models import TreasuryTransfer, JournalEntry
        from services.accounting_service import AccountingService
        t = self.db.query(TreasuryTransfer).get(transfer_id)
        if not t:
            raise ValueError(f"Transfer {transfer_id} not found")
        was_posted = t.status == "posted"
        from services.workflow_service import WorkflowService
        WorkflowService(self.db).cancel(t, user)
        if was_posted:
            self.restore_balance(t.from_account_id, D(t.amount))
            self.deduct_balance(t.to_account_id, D(t.net_amount))
            if D(t.fee) > DECIMAL_ZERO:
                self.restore_balance(t.from_account_id, D(t.fee))
                entry = self.db.query(JournalEntry).filter(
                    JournalEntry.source_type == "transfer",
                    JournalEntry.source_id == t.id,
                    JournalEntry.is_reversal == 0,
                ).first()
                if entry:
                    AccountingService(self.db).reverse_entry(
                        entry.id,
                        created_by=getattr(user, "username", "system") if user else "system",
                    )
        self.db.flush()

    def post_closing(self, closing_id: int, user=None):
        from models import CashClosing
        from services.accounting_service import AccountingService
        from services.workflow_service import WorkflowService
        c = self.db.query(CashClosing).get(closing_id)
        if not c:
            raise ValueError(f"CashClosing {closing_id} not found")
        WorkflowService(self.db).post(c, user)
        diff = D(c.difference)
        if diff != DECIMAL_ZERO:
            asc = AccountingService(self.db)
            if diff > DECIMAL_ZERO:
                lines = [(asc._acc_id("treasury"), diff, DECIMAL_ZERO),
                         (asc._acc_id("cash_surplus"), DECIMAL_ZERO, diff)]
            else:
                lines = [(asc._acc_id("cash_shortage"), abs(diff), DECIMAL_ZERO),
                         (asc._acc_id("treasury"), DECIMAL_ZERO, abs(diff))]
            asc.post(lines=lines, source_type="closing", source_id=c.id,
                     description=f"تسوية جرد #{c.id}: {c.reason or ''}",
                     created_by=getattr(user, "username", "system") if user else "system")
        self.db.flush()

    def cancel_closing(self, closing_id: int, user=None):
        from models import CashClosing, JournalEntry
        from services.accounting_service import AccountingService
        from services.workflow_service import WorkflowService
        c = self.db.query(CashClosing).get(closing_id)
        if not c:
            raise ValueError(f"CashClosing {closing_id} not found")
        WorkflowService(self.db).cancel(c, user)
        if c.status == "posted":
            diff = D(c.difference)
            if diff != DECIMAL_ZERO:
                entry = self.db.query(JournalEntry).filter(
                    JournalEntry.source_type == "closing",
                    JournalEntry.source_id == c.id,
                    JournalEntry.is_reversal == 0,
                ).first()
                if entry:
                    AccountingService(self.db).reverse_entry(
                        entry.id,
                        created_by=getattr(user, "username", "system") if user else "system",
                    )
        self.db.flush()
