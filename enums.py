# models/enums.py
from enum import Enum

class OrderStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    PAID = "paid"
    CANCELLED = "cancelled"
    AWAITING_CLARIFICATION = "awaiting_clarification"
    NEEDS_NEW_DOCS = "needs_new_docs"

class DocumentType(str, Enum):
    PHOTO = "photo"
    PDF = "pdf"
    DOC = "doc"
    OTHER = "other"

class PaymentStatus(str, Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    REFUNDED = "refunded"

class DiscountType(str, Enum):
    PERCENT = "percent"
    FIXED = "fixed"