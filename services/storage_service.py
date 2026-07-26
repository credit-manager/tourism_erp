"""
StorageService — تخزين آمن للملفات الحساسة خارج مجلد static.

المزايا:
- توليد أسماء عشوائية آمنة (uuid4) بحيث لا يُكشف الاسم الأصلي ولا مسار النظام.
- التحقق من الامتداد + MIME الحقيقي (قراءة Magic bytes) وليس فقط الاسم.
- التحقق من الحجم الأقصى.
- منع Path Traversal: المسار الناتج يجب أن يكون داخل مجلد التخزين فقط.
- منع الملفات التنفيذية (exe/dll/bat/ps1/sh/php/py/...) وأي ملف يبدأ بـ MZ أو #!.
- فحص Antivirus عند الإنتاج (clamscan/clamdscan) إن وُجد مثبّتاً.
- حساب بصمة SHA-256 للتحقق من التكرار/التلاعب.
"""
import os
import io
import uuid
import hashlib
import subprocess
import mimetypes

# مجلد التخزين خارج static (لا يُخدم مباشرة عبر الويب)
SECURE_STORAGE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "storage", "secure")

# الامتدادات المسموحة
ALLOWED_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp",
    ".pdf",
    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".txt", ".csv", ".rtf",
    ".zip",
}

# الامتدادات التنفيذية الممنوعة صراحة (إضافة لحماية Magic bytes)
FORBIDDEN_EXECUTABLE_EXTS = {
    ".exe", ".dll", ".bat", ".cmd", ".com", ".msi", ".ps1", ".psm1",
    ".sh", ".bash", ".bin", ".run", ".app", ".jar", ".vb", ".vbs", ".js",
    ".jse", ".wsf", ".scr", ".pif", ".scr", ".php", ".py", ".pyw", ".rb",
    ".cpl", ".gadget", ".inf", ".reg", ".scf", ".lnk",
}

# حد الحجم الافتراضي (10MB)
DEFAULT_MAX_SIZE = 10 * 1024 * 1024

# خريطة Magic bytes -> (mime مقبول، امتداد مقترح)
MAGIC_SIGNATURES = [
    (b"\xFF\xD8\xFF", "image/jpeg", ".jpg"),
    (b"\x89PNG\r\n\x1A\n", "image/png", ".png"),
    (b"GIF87a", "image/gif", ".gif"),
    (b"GIF89a", "image/gif", ".gif"),
    (b"RIFF....WEBP", "image/webp", ".webp"),
    (b"%PDF-", "application/pdf", ".pdf"),
    (b"PK\x03\x04", "application/zip", ".zip"),          # docx/xlsx/pptx/zip كلها ZIP
    (b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1", "application/msword", ".doc"),  # doc/xls/ppt القديمة
    (b"MZ", "application/x-msdownload", ".exe"),          # ملف تنفيذي ويندوز
]


class StorageError(Exception):
    """خطأ في التحقق من الملف."""


class StorageSecurityError(StorageError):
    """محاولة رفع ملف خطير (تنفيذي / traversal / MIME مزيف)."""


def _detect_mime_by_magic(head: bytes):
    """يُرجع (mime, ext) من أول بايتات الملف، أو (None, None)."""
    for sig, mime, ext in MAGIC_SIGNATURES:
        pattern = sig
        if b"." in sig:  # نمط به أحرف بدل (مثل RIFF....WEBP)
            if len(head) >= len(pattern) and all(
                head[i] == pattern[i] or pattern[i] == ord(".") for i in range(len(pattern))
            ):
                return mime, ext
        else:
            if head.startswith(sig):
                return mime, ext
    return None, None


def _is_executable_magic(head: bytes) -> bool:
    """كشف الملفات التنفيذية عبر Magic bytes."""
    # PE / MZ (ويندوز)
    if head.startswith(b"MZ"):
        return True
    # ELF
    if head.startswith(b"\x7FELF"):
        return True
    # Mach-O
    if head[:4] in (b"\xCA\xFE\xBA\xBE", b"\xFE\xED\xFA\xCE", b"\xFE\xED\xFA\xCF", b"\xC0\xFA\xFE\xBA"):
        return True
    # شل سكريبت تبدأ بـ #!
    if head.startswith(b"#!"):
        return True
    return False


def _clamav_scan(path: str, required: bool = False) -> None:
    """فحص Antivirus باستخدام clamscan/clamdscan.

    - في التطوير: لو مش مثبّت، نتجاوز بهدوء.
    - في الإنتاج/الاستيج (required=True): لو مش مثبّت نرفض الرفع (fail-closed)
      عشان منحصلش على ملفات من غير فحص.
    """
    for cmd in ("clamdscan", "clamscan"):
        exe = shutil_which(cmd)
        if not exe:
            continue
        try:
            res = subprocess.run(
                [exe, "--no-summary", "--stdout", path],
                capture_output=True, timeout=60,
            )
        except Exception:
            continue
        # clamscan: كود الخروج 0 = نظيف، 1 = فيروس، 2 = خطأ
        if res.returncode == 1:
            raise StorageSecurityError("الملف يحتوي على برمجيات خبيثة (Antivirus)")
        if res.returncode == 0:
            return
    # لا يوجد clamav مثبّت
    if required:
        raise StorageSecurityError("تعذّر فحص الملف ببرنامج الحماية (Antivirus غير متوفر)")
    # التطوير: نتجاوز بهدوء


def shutil_which(name: str):
    from shutil import which
    return which(name)


class StorageService:
    def __init__(self, storage_dir: str = SECURE_STORAGE_DIR, max_size: int = DEFAULT_MAX_SIZE,
                 environment: str = "development"):
        self.storage_dir = storage_dir
        self.max_size = max_size
        self.environment = environment
        os.makedirs(self.storage_dir, exist_ok=True)

    def _safe_join(self, name: str) -> str:
        """يربط الاسم بمجلد التخزين ويتأكد أنه لا يخرج منه (منع traversal)."""
        base = os.path.abspath(self.storage_dir)
        target = os.path.abspath(os.path.join(base, name))
        if target != base and not target.startswith(base + os.sep):
            raise StorageSecurityError("محاولة الوصول لمسار غير مسموح (Path Traversal)")
        return target

    def save(self, file, owner_user_id=None, category="doc",
             record_type=None, record_id=None, db=None, request=None) -> "SecureFile":
        """يحفظ الملف بعد التحقق الكامل ويسجّل سجل SecureFile + Audit."""
        from models import SecureFile, AuditLog, SessionLocal
        filename = getattr(file, "filename", None)
        if not filename:
            raise StorageError("لا يوجد اسم ملف")
        original_name = os.path.basename(filename)  # إزالة أي مسارات من الاسم

        # قراءة المحتوى كاملاً للتحقق
        content = file.file.read()
        size = len(content)
        if size == 0:
            raise StorageError("الملف فارغ")
        if size > self.max_size:
            raise StorageError(f"الملف كبير جداً (الحد الأقصى {self.max_size // (1024*1024)}MB)")

        head = content[:64]

        # 1) منع التنفيذي عبر Magic bytes
        if _is_executable_magic(head):
            raise StorageSecurityError("نوع الملف مرفوض: ملف تنفيذي")

        # 2) التحقق من الامتداد
        ext = os.path.splitext(original_name)[1].lower()
        if ext in FORBIDDEN_EXECUTABLE_EXTS:
            raise StorageSecurityError(f"الامتداد مرفوض: {ext}")
        if ext not in ALLOWED_EXTENSIONS:
            raise StorageError(f"الامتداد غير مدعوم: {ext}")

        # 3) التحقق من MIME الحقيقي
        mime, magic_ext = _detect_mime_by_magic(head)
        magic_confirmed = mime is not None
        if not magic_confirmed:
            mime = mimetypes.guess_type(original_name)[0] or "application/octet-stream"
        # الأنواع التي يمكن التحقق منها عبر Magic bytes: نرفض إن لم تتطابق (منع تزييف الامتداد)
        MAGIC_VERIFIABLE = {".pdf", ".jpg", ".jpeg", ".png", ".gif", ".webp",
                            ".docx", ".xlsx", ".pptx", ".zip", ".doc", ".xls", ".ppt"}
        if not magic_confirmed and ext in MAGIC_VERIFIABLE:
            raise StorageSecurityError("محتوى الملف لا يطابق الامتداد (تزييف محتمل)")
        # رفض أي شيء يشبه تنفيذياً
        if mime in ("application/x-msdownload", "application/x-executable",
                    "application/x-sh", "text/x-sh", "text/x-python",
                    "application/x-dosexec", "application/javascript"):
            raise StorageSecurityError(f"نوع الملف مرفوض: {mime}")

        # 4) الموافقة بين الامتداد والـ MIME (تجنب تزييف الامتداد)
        self._assert_ext_mime_consistent(ext, mime)

        # توليد اسم عشوائي آمن
        stored_name = uuid.uuid4().hex + ext
        dest = self._safe_join(stored_name)

        # 5) فحص Antivirus عند الإنتاج
        # نكتب أولاً ثم نفحص (لأن clamav يحتاج ملفاً على القرص)
        with open(dest, "wb") as f:
            f.write(content)
        if self.environment in ("production", "staging"):
            try:
                _clamav_scan(dest, required=True)
            except StorageSecurityError:
                if os.path.exists(dest):
                    os.remove(dest)
                raise

        sha = hashlib.sha256(content).hexdigest()

        # تسجيل في DB
        sess = db if db is not None else SessionLocal()
        own = False
        try:
            sf = SecureFile(
                owner_user_id=owner_user_id,
                category=category,
                record_type=record_type,
                record_id=record_id,
                stored_name=stored_name,
                original_name=original_name,
                mime=mime,
                size=size,
                sha256=sha,
            )
            sess.add(sf)
            sess.flush()
            # تسجيل الرفع في Audit
            user = None
            if request is not None:
                user = getattr(request.state, "user", None)
            username = (user.username if user else "?")
            role = (user.role if user else "")
            sess.add(AuditLog(
                timestamp=__import__("datetime").datetime.utcnow(),
                username=username, role=role,
                action="upload", table_name="secure_files",
                record_id=sf.id,
                summary=f"رفع ملف: {original_name} ({mime}, {size} بايت) -> {category}",
                reason=None,
            ))
            if db is None:
                sess.commit()
            else:
                # نترك الـ commit للمُستدعي ضمن معاملته
                sess.flush()
            return sf
        except Exception:
            if os.path.exists(dest):
                os.remove(dest)
            if db is None:
                sess.rollback()
            raise
        finally:
            if db is None:
                sess.close()

    def _assert_ext_mime_consistent(self, ext: str, mime: str):
        """يتأكد أن الامتداد والـ MIME متوافقان لتجنب تزييف الامتداد."""
        groups = {
            "image": {".jpg", ".jpeg", ".png", ".gif", ".webp"},
            "pdf": {".pdf"},
            "office_zip": {".docx", ".xlsx", ".pptx", ".zip"},
            "office_legacy": {".doc", ".xls", ".ppt"},
            "text": {".txt", ".csv", ".rtf"},
        }
        norm_mime = mime.split(";")[0].lower()
        if norm_mime.startswith("image/"):
            ok = ext in groups["image"]
        elif norm_mime == "application/pdf":
            ok = ext == ".pdf"
        elif norm_mime in ("application/zip", "application/vnd.openxmlformats-officedocument"):
            ok = ext in groups["office_zip"]
        elif norm_mime in ("application/msword", "application/vnd.ms-excel", "application/vnd.ms-powerpoint"):
            ok = ext in groups["office_legacy"]
        elif norm_mime.startswith("text/"):
            ok = ext in groups["text"]
        else:
            ok = True  # أنواع أخرى مقبولة طالما اجتازت الفحص
        if not ok:
            raise StorageSecurityError(f"عدم تطابق بين الامتداد {ext} والنوع {mime}")

    def read_path(self, stored_name: str) -> str:
        """يُرجع المسار الآمن للملف (بعد التحقق من traversal)."""
        return self._safe_join(os.path.basename(stored_name))

    def delete(self, sf, db=None, request=None):
        """يحذف الملف فعلياً ويسجّل الحذف في Audit."""
        from models import AuditLog, SessionLocal
        path = self.read_path(sf.stored_name)
        if os.path.exists(path):
            os.remove(path)
        sess = db if db is not None else SessionLocal()
        try:
            user = None
            if request is not None:
                user = getattr(request.state, "user", None)
            sess.add(AuditLog(
                timestamp=__import__("datetime").datetime.utcnow(),
                username=(user.username if user else "?"),
                role=(user.role if user else ""),
                action="delete", table_name="secure_files", record_id=sf.id,
                summary=f"حذف ملف: {sf.original_name} ({sf.category})",
                reason=None,
            ))
            if db is None:
                sess.commit()
            else:
                sess.flush()
        finally:
            if db is None:
                sess.close()

    def log_download(self, sf, db=None, request=None):
        """يسجّل عملية تنزيل في Audit."""
        from models import AuditLog, SessionLocal
        sess = db if db is not None else SessionLocal()
        try:
            user = None
            if request is not None:
                user = getattr(request.state, "user", None)
            sess.add(AuditLog(
                timestamp=__import__("datetime").datetime.utcnow(),
                username=(user.username if user else "?"),
                role=(user.role if user else ""),
                action="download", table_name="secure_files", record_id=sf.id,
                summary=f"تنزيل ملف: {sf.original_name} ({sf.category})",
                reason=None,
            ))
            if db is None:
                sess.commit()
            else:
                sess.flush()
        finally:
            if db is None:
                sess.close()


# نسخة وحيدة جاهزة للاستخدام
storage_service = StorageService()
