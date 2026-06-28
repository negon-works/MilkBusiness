import calendar
from datetime import date
from decimal import Decimal
from urllib.parse import quote

from .models import BusinessSetting, DailyEntry


def whatsapp_link(raw_number, message):
    digits = ''.join(ch for ch in raw_number if ch.isdigit())
    return f'https://wa.me/{digits}?text={quote(message)}'


def month_name(month):
    return calendar.month_name[month]


def build_reminder_text(customer_name, month, amount):
    return (
        f'Hello {customer_name},\n\n'
        f'Your milk bill for {month} is Rs {amount}.\n\n'
        'Please settle when possible.'
    )


def build_bill_text(customer_name, month_year, total_litre, total_days, total_amount):
    return (
        f'Hello {customer_name},\n\n'
        f'Your milk bill for {month_year}:\n\n'
        f'Total Litres: {total_litre} L\n'
        f'Total Days: {total_days}\n'
        f'Total Amount: Rs {total_amount}\n\n'
        'Thank you'
    )


def compute_entry_amount(entry):
    rate = BusinessSetting.get_solo().milk_rate_per_litre
    return entry.delivered_litre * rate


def month_bounds(year, month):
    start = date(year, month, 1)
    end_day = calendar.monthrange(year, month)[1]
    end = date(year, month, end_day)
    return start, end


def get_or_create_daily_entry(customer, selected_date):
    entry, _ = DailyEntry.objects.get_or_create(
        customer=customer,
        date=selected_date,
        defaults={
            'morning_litre': Decimal('0.00'),
            'evening_litre': Decimal('0.00'),
            'morning_status': DailyEntry.STATUS_DELIVERED,
            'evening_status': DailyEntry.STATUS_DELIVERED,
        },
    )
    return entry
