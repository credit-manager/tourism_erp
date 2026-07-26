"""
قاموس الترجمة الأساسي للواجهة عربي / إنجليزي.

الاستخدام اليدوي داخل القوالب:
{{ t(request, 'dashboard') }}

الاستخدام التلقائي:
AUTO_TRANSLATE يُستخدم لتحويل النصوص العربية الظاهرة في الصفحات إلى إنجليزي
عن طريق سكريبت عام في base.html.
"""

I18N = {
    # ===== عام =====
    "app_name": {"ar": "Tourism ERP", "en": "Tourism ERP"},
    "dashboard": {"ar": "الرئيسية", "en": "Dashboard"},
    "dashboard_title": {"ar": "لوحة التحكم الرئيسية", "en": "Main Dashboard"},
    "dashboard_subtitle": {
        "ar": "نظرة منظمة على الحجوزات، الإيرادات، التحصيلات، الفنادق، وحركة اليوم.",
        "en": "Organized overview of bookings, revenue, collections, hotels, and today's activity."
    },

    # ===== القائمة الجانبية =====
    "reservations": {"ar": "الحجوزات", "en": "Reservations"},
    "booking_board": {"ar": "لوحة الحجز", "en": "Booking Board"},
    "all_booking": {"ar": "كل الحجوزات", "en": "All Bookings"},
    "services": {"ar": "الخدمات", "en": "Services"},
    "customers": {"ar": "العملاء", "en": "Customers"},
    "suppliers": {"ar": "الموردين", "en": "Suppliers"},
    "hotels": {"ar": "الفنادق", "en": "Hotels"},
    "collections": {"ar": "التحصيلات", "en": "Receipts"},
    "treasury": {"ar": "الخزنة", "en": "Cash Management"},
    "expenses": {"ar": "المصروفات", "en": "Expenses"},
    "employees": {"ar": "الموظفين", "en": "Employees"},
    "attendance": {"ar": "الحضور", "en": "Attendance"},
    "payroll": {"ar": "الرواتب الشهرية", "en": "Monthly Payroll"},
    "contracts": {"ar": "العقود", "en": "Contracts"},
    "transport": {"ar": "النقل", "en": "Transportations"},
    "tickets": {"ar": "التذاكر", "en": "Tickets"},
    "umrah": {"ar": "العمرة", "en": "Umrah"},
    "tourism_files": {"ar": "ملفات السياحة", "en": "Tourism Files"},
    "police": {"ar": "إخطار الشرطة", "en": "Police Notification"},
    "reports": {"ar": "التقارير", "en": "Reports"},
    "supplier_payments": {"ar": "سداد الموردين", "en": "Supplier Payments"},
    "accounting": {"ar": "الحسابات", "en": "General Ledger"},
    "withdrawals": {"ar": "سحب الموظفين", "en": "Employee Withdrawals"},
    "settings": {"ar": "الإعدادات", "en": "Settings"},
    "audit_log": {"ar": "سجل التتبع", "en": "Audit Log"},
    "management": {"ar": "الإدارة", "en": "Management"},

    # ===== أزرار وعمليات =====
    "search": {"ar": "بحث سريع...", "en": "Quick search..."},
    "add_new": {"ar": "إضافة", "en": "Add"},
    "add": {"ar": "إضافة", "en": "Add"},
    "save": {"ar": "حفظ", "en": "Save"},
    "edit": {"ar": "تعديل", "en": "Edit"},
    "delete": {"ar": "حذف", "en": "Delete"},
    "view": {"ar": "عرض", "en": "View"},
    "open": {"ar": "فتح", "en": "Open"},
    "cancel": {"ar": "إلغاء", "en": "Cancel"},
    "actions": {"ar": "إجراءات", "en": "Actions"},
    "logout": {"ar": "تسجيل الخروج", "en": "Logout"},
    "apply_filter": {"ar": "تطبيق الفلتر", "en": "Apply Filter"},
    "export_excel": {"ar": "تصدير Excel", "en": "Export Excel"},
    "print_pdf": {"ar": "طباعة / PDF", "en": "Print / PDF"},

    # ===== الداشبورد =====
    "total_revenue": {"ar": "إجمالي الإيرادات", "en": "Total Revenue"},
    "total_sales": {"ar": "إجمالي المبيعات", "en": "Total Sales"},
    "total_expenses": {"ar": "إجمالي المصروفات", "en": "Total Expenses"},
    "net_profit": {"ar": "صافي الربح", "en": "Net Profit"},
    "gross_profit": {"ar": "الربح الإجمالي", "en": "Gross Profit"},
    "total_bookings": {"ar": "إجمالي الحجوزات", "en": "Total Bookings"},
    "pending_payments": {"ar": "مدفوعات معلقة", "en": "Pending Payments"},
    "today_arrivals": {"ar": "وصول اليوم", "en": "Today Arrivals"},
    "today_departures": {"ar": "مغادرة اليوم", "en": "Today Departures"},
    "today": {"ar": "اليوم", "en": "Today"},
    "last_14_days": {"ar": "آخر 14 يوم", "en": "Last 14 Days"},
    "booking_performance": {"ar": "أداء الحجوزات والإيرادات", "en": "Bookings & Revenue Performance"},
    "booking_status": {"ar": "الحالة العامة للحجوزات", "en": "Booking Status"},
    "recent_bookings": {"ar": "آخر الحجوزات", "en": "Recent Bookings"},
    "today_activity": {"ar": "حركة اليوم", "en": "Today's Activity"},
    "top_destinations": {"ar": "أعلى الوجهات", "en": "Top Destinations"},
    "revenue_vs_cost": {"ar": "الإيرادات مقابل التكلفة", "en": "Revenue vs Cost"},
    "profit_summary": {"ar": "ملخص الربحية", "en": "Profit Summary"},
    "booking_sources": {"ar": "مصادر الحجوزات", "en": "Booking Sources"},
    "top_agents": {"ar": "أفضل المندوبين", "en": "Top Agents"},
    "highest_pending": {"ar": "أعلى المبالغ المعلقة", "en": "Highest Outstanding Amounts"},

    # ===== الجداول =====
    "booking_no": {"ar": "رقم الحجز", "en": "Booking No."},
    "date": {"ar": "التاريخ", "en": "Date"},
    "customer": {"ar": "العميل", "en": "Customer"},
    "guest": {"ar": "النزيل", "en": "Guest"},
    "guest_name": {"ar": "اسم العميل", "en": "Guest Name"},
    "hotel": {"ar": "الفندق", "en": "Hotel"},
    "arrival": {"ar": "الوصول", "en": "Arrival"},
    "departure": {"ar": "المغادرة", "en": "Departure"},
    "amount": {"ar": "المبلغ", "en": "Amount"},
    "payment": {"ar": "الدفع", "en": "Payment"},
    "status": {"ar": "الحالة", "en": "Status"},
    "name": {"ar": "الاسم", "en": "Name"},
    "phone": {"ar": "الهاتف", "en": "Phone"},
    "type": {"ar": "النوع", "en": "Type"},
    "balance": {"ar": "الرصيد", "en": "Balance"},
    "city": {"ar": "المدينة", "en": "City"},
    "price": {"ar": "السعر", "en": "Price"},
    "cost": {"ar": "التكلفة", "en": "Cost"},
    "sale": {"ar": "البيع", "en": "Sale"},
    "profit": {"ar": "الربح", "en": "Profit"},
    "notes": {"ar": "ملاحظات", "en": "Notes"},
    "description": {"ar": "الوصف", "en": "Description"},
    "category": {"ar": "التصنيف", "en": "Category"},

    # ===== حالات =====
    "paid": {"ar": "مسدد", "en": "Paid"},
    "open_status": {"ar": "مفتوح", "en": "Open"},
    "pending": {"ar": "معلق", "en": "Pending"},
    "active": {"ar": "نشط", "en": "Active"},
    "follow": {"ar": "متابعة", "en": "Follow"},
    "important": {"ar": "مهم", "en": "Important"},
    "confirmed": {"ar": "مؤكدة", "en": "Confirmed"},
    "cancelled": {"ar": "ملغية", "en": "Cancelled"},
    "draft": {"ar": "مسودة", "en": "Draft"},
    "checked_in": {"ar": "تسكين", "en": "Checked In"},
    "checked_out": {"ar": "مغادرة", "en": "Checked Out"},
    "closed": {"ar": "مغلق", "en": "Closed"},
    "expired": {"ar": "منتهي", "en": "Expired"},

    # ===== رسائل فارغة =====
    "no_data": {"ar": "لا توجد بيانات", "en": "No data"},
    "no_bookings": {"ar": "لا توجد حجوزات بعد", "en": "No bookings yet"},
    "no_reservations": {"ar": "لا توجد حجوزات", "en": "No reservations"},
    "no_destinations": {"ar": "لا توجد بيانات وجهات", "en": "No destination data"},
    "no_agents": {"ar": "لا توجد بيانات مندوبين", "en": "No agent data"},
    "no_pending_amounts": {"ar": "لا توجد مبالغ معلقة", "en": "No outstanding amounts"},
    "booking_statement": {"ar": "كشف حساب الحجز", "en": "Booking Statement"},
    "view_booking_statement": {"ar": "عرض كشف حساب الحجز", "en": "View Booking Statement"},
    "account_movements": {"ar": "حركة الحساب", "en": "Account Movements"},
    "invoice_amount": {"ar": "قيمة الفاتورة", "en": "Invoice Amount"},
    "total_paid": {"ar": "إجمالي المسدد", "en": "Total Paid"},
    "remaining_balance": {"ar": "المتبقي", "en": "Remaining Balance"},
    "cost_and_profit": {"ar": "التكلفة والربح", "en": "Cost & Profit"},
    "no_movements_for_booking": {"ar": "لا توجد حركات لهذا الحجز", "en": "No movements for this booking"},
    "entry_type_invoice": {"ar": "فاتورة", "en": "Invoice"},
    "entry_type_payment": {"ar": "دفع", "en": "Payment"},
    "entry_type_supplier_payment": {"ar": "دفعة مورد", "en": "Supplier Payment"},
    "entry_type_refund": {"ar": "مرتجع", "en": "Refund"},
    "account_summary": {"ar": "ملخص الحساب", "en": "Account Summary"},
}


# ترجمة تلقائية للنصوص العربية الظاهرة في الصفحات
# المفتاح عربي كما يظهر في HTML، والقيمة إنجليزي.
AUTO_TRANSLATE = {
    value["ar"]: value["en"]
    for value in I18N.values()
    if value.get("ar") and value.get("en")
}

# إضافات نصوص طويلة أو مختلفة عن مفاتيح I18N
AUTO_TRANSLATE.update({
    "نظام إدارة سياحة متكامل": "Integrated Tourism Management System",
    "نظام إدارة سياحة متكامل للحجوزات، التحصيلات، الفنادق، والخزنة.": "Integrated tourism management system for reservations, collections, hotels, and treasury.",

    "إجمالي عدد الحجوزات داخل النظام": "Total number of bookings in the system",
    "إجمالي أسعار البيع للحجوزات": "Total booking sales amount",
    "قبل العمولات والمصروفات": "Before commissions and expenses",
    "إجمالي المتبقي على العملاء": "Total outstanding from customers",
    "حجوزات متوقع وصولها اليوم": "Bookings expected to arrive today",
    "حجوزات تغادر اليوم": "Bookings departing today",

    "تحصيلات معلقة": "Pending Collections",
    "إجمالي العمولات": "Total Commissions",
    "لا توجد ملفات مؤرشفة بعد": "No archived files yet",
    "لا توجد إخطارات مسجّلة بعد": "No notifications registered yet",
    "لا توجد رحلات نقل مسجّلة بعد": "No transport trips registered yet",
    "لا توجد تذاكر مسجّلة بعد": "No tickets registered yet",
    "لا توجد برامج عمرة مسجّلة بعد": "No Umrah packages registered yet",
    "لا يوجد عملاء بعد": "No customers yet",
    "لا توجد مصروفات في هذه الفترة": "No expenses in this period",
    "لا توجد حجوزات في هذه الفترة": "No bookings in this period",

    "من تاريخ": "From Date",
    "إلى تاريخ": "To Date",
    "الفترة من": "Period from",
    "إلى": "to",

    "إضافة حجز": "Add Reservation",
    "إضافة حجز جديد": "Add New Reservation",
    "حفظ الحجز": "Save Reservation",
    "حفظ التحصيل وتوزيعه": "Save Collection & Allocation",
    "تحصيل لأكثر من حجز": "Collect Multiple Bookings",
    "مدفوعات خارجة من السيستم": "Outgoing System Payments",
    "إجمالي الخارج": "Total Outgoing",
    "إضافة جهة أخرى": "Add Another Payee",

    "اسم الفندق": "Hotel Name",
    "فندق جديد": "New Hotel",
    "فندق جديد لو مش هو": "New hotel if not listed",
    "الفندق ده موجود بالفعل، سيتم استخدام الفندق الموجود بدل إنشاء فندق جديد.": "This hotel already exists. The existing hotel will be used instead of creating a duplicate.",

    "اسم الموظف": "Employee Name",
    "إضافة موظف جديد": "Add New Employee",
    "إنشاء الموظف واختياره": "Create Employee & Select",
    "رقم الهاتف": "Phone Number",

    "مدير النظام": "System Admin",
    "محاسب": "Accountant",
    "موظف حجوزات": "Reservations Staff",

    "سعر البيع": "Sale Price",
    "سعر التكلفة": "Cost Price",
    "المسدد": "Paid",
    "المتبقي": "Remaining",
    "المورد": "Supplier",
    "تاريخ الحجز": "Booking Date",
    "تاريخ الوصول": "Check-in Date",
    "تاريخ المغادرة": "Check-out Date",
    "الغرفة": "Room",
    "نوع الغرفة": "Room Type",
    "عدد الغرف": "Rooms",
    "عدد الليالي": "Nights",
    "الجنسية": "Nationality",
    "رقم الجواز": "Passport No.",

    "كشف حساب الحجز": "Booking Statement",
    "حركة الحساب": "Account Movements",
    "قيمة الفاتورة": "Invoice Amount",
    "إجمالي المسدد": "Total Paid",
    "التكلفة والربح": "Cost & Profit",
    "لا توجد حركات لهذا الحجز": "No movements for this booking",
    "فاتورة": "Invoice",
    "فاتورة الحجز": "Booking Invoice",
    "دفعة": "Payment",
    "دفعة مورد": "Supplier Payment",
    "دفعة لمورد": "Payment to Supplier",
    "تحصيل": "Collection",
    "مرتجع": "Refund",
    "مرتجع (إلغاء الحجز)": "Refund (Cancellation)",
    "ملخص الحساب": "Account Summary",
    "مدين": "Debit",
    "دائن": "Credit",
    "الرصيد": "Balance",
    "النوع": "Type",
    "الوصف": "Description",
    "المرجع": "Reference",
    "التاريخ": "Date",
    "حركة": "entries",
    "لوحة الحجز": "Booking Board",

    # ===== عناوين breadcrumbs والأزرار =====
    "طباعة قسيمة": "Print Voucher",
    "كشف حساب": "Statement",
    "إرسال تأكيد": "Send Confirmation",
    "نسخ الحجز": "Copy Booking",
    "إضافة عميل جديد": "Add New Customer",
    "إدارة العملاء": "Manage Customers",
    "إدارة الموظفين": "Manage Employees",
    "إدارة الموردين": "Manage Suppliers",
    "حذف جهة الدفع": "Delete Payee",

    # ===== رسائل JavaScript =====
    "متبقي: ": "Remaining: ",
    "تم السداد بالكامل": "Fully Paid",
    "زيادة: ": "Overpayment: ",
    "جاري الحفظ...": "Saving...",
    "اكتب اسم العميل أولاً.": "Please enter customer name first.",
    "اكتب اسم الموظف أولاً.": "Please enter employee name first.",
    "اسم الفندق مطلوب.": "Hotel name is required.",
    "اسم الشركة / المورد مطلوب.": "Company/Supplier name is required.",
})

# قاموس إضافي لعناوين title الأزرار غير المغطاة بـ I18N
TOOLTIP_TRANSLATE = {
    "الكل": "All",
    "إضافة": "Add",
    "تعديل": "Edit",
    "حذف": "Delete",
    "عرض": "View",
    "بحث": "Search",
    "حفظ": "Save",
    "إلغاء": "Cancel",
}

AUTO_TRANSLATE.update(TOOLTIP_TRANSLATE)


def get_text_map(lang: str = "en"):
    """
    يرجع قاموس الترجمة التلقائية حسب اللغة.
    عند اللغة الإنجليزية: يرجع عربي -> إنجليزي.
    عند العربي: يرجع قاموس فاضي لأن النصوص الأصلية عربية.
    """
    if lang == "en":
        return AUTO_TRANSLATE
    return {}


def translate_key(key: str, lang: str = "ar") -> str:
    """
    ترجمة مفتاح محدد.
    """
    item = I18N.get(key)
    if not item:
        return key
    return item.get(lang, item.get("ar", key))


def translate_text(text: str, lang: str = "en") -> str:
    """
    ترجمة نص عربي ظاهر كما هو.
    """
    if lang != "en":
        return text

    clean = " ".join(str(text or "").split())
    return AUTO_TRANSLATE.get(clean, text)