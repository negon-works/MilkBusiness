import calendar
import csv
import io
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Exists, F, OuterRef, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .forms import (
    BusinessSettingForm,
    CowForm,
    CowMedicineRecordForm,
    CowMarketplaceListingForm,
    CowTreatmentLogForm,
    CustomerForm,
    DailyEntryModalForm,
    DiseaseTypeForm,
    FeedSackForm,
    MonthYearForm,
)
from .models import (
    BusinessSetting,
    Cow,
    CowMedicineRecord,
    CowMarketplaceListing,
    CowDiseaseMonthlyStatus,
    CowTreatmentLog,
    Customer,
    DailyEntry,
    DeliveryDayStatus,
    DiseaseType,
    FeedSackAdditionalCost,
    FeedSackItem,
    FeedSackPurchase,
    MonthlyBill,
)
from .utils import (
    build_bill_text,
    build_reminder_text,
    compute_entry_amount,
    get_or_create_daily_entry,
    month_bounds,
    month_name,
    whatsapp_link,
)


def _safe_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _delivery_snapshot(target_date):
    is_holiday = DeliveryDayStatus.objects.filter(day=target_date, is_holiday=True).exists()
    entries = DailyEntry.objects.filter(date=target_date).select_related('customer')
    morning_customers_count = Customer.objects.filter(morning_litre__gt=0).count()
    evening_customers_count = Customer.objects.filter(evening_litre__gt=0).count()

    morning_checked = 0
    evening_checked = 0
    for entry in entries:
        if entry.customer.morning_litre > 0 and (
            entry.morning_status == DailyEntry.STATUS_NO_MILK or entry.morning_litre > 0
        ):
            morning_checked += 1
        if entry.customer.evening_litre > 0 and (
            entry.evening_status == DailyEntry.STATUS_NO_MILK or entry.evening_litre > 0
        ):
            evening_checked += 1

    morning_pending = max(morning_customers_count - morning_checked, 0)
    evening_pending = max(evening_customers_count - evening_checked, 0)
    if is_holiday:
        morning_pending = 0
        evening_pending = 0

    now_dt = timezone.now()
    if timezone.is_aware(now_dt):
        now_local = now_dt.astimezone(ZoneInfo('Asia/Kolkata'))
    else:
        now_local = now_dt
    show_morning_alert = now_local.hour >= 6 and morning_pending > 0
    show_evening_alert = now_local.hour >= 15 and evening_pending > 0

    morning_pending_ui = morning_pending if now_local.hour >= 6 else 0
    evening_pending_ui = evening_pending if now_local.hour >= 15 else 0

    return {
        'morning_customers_count': morning_customers_count,
        'evening_customers_count': evening_customers_count,
        'morning_checked': morning_checked,
        'evening_checked': evening_checked,
        'morning_pending': morning_pending,
        'evening_pending': evening_pending,
        'morning_pending_ui': morning_pending_ui,
        'evening_pending_ui': evening_pending_ui,
        'show_morning_alert': show_morning_alert,
        'show_evening_alert': show_evening_alert,
    }


def _is_shift_checked(entry, mode):
    if mode == 'morning':
        return entry.morning_status == DailyEntry.STATUS_NO_MILK or entry.morning_litre > 0
    return entry.evening_status == DailyEntry.STATUS_NO_MILK or entry.evening_litre > 0


def _shift_counts_for_date(target_date, mode):
    if DeliveryDayStatus.objects.filter(day=target_date, is_holiday=True).exists():
        return 0, 0
    if mode == 'morning':
        customers = Customer.objects.filter(morning_litre__gt=0)
    else:
        customers = Customer.objects.filter(evening_litre__gt=0)
    entries = DailyEntry.objects.filter(date=target_date, customer__in=customers).select_related('customer')
    checked = sum(1 for entry in entries if _is_shift_checked(entry, mode))
    total = customers.count()
    return checked, total


def _missed_delivery_notifications_count(today=None):
    today = today or date.today()
    return len(_collect_missed_delivery_days(today=today))


def _collect_missed_delivery_days(today=None, start_date=None, lookback_days=45):
    today = today or date.today()
    setting = BusinessSetting.get_solo()
    start_date = start_date or setting.data_reset_date
    oldest_entry = (
        DailyEntry.objects.filter(date__gte=start_date).order_by('date').values_list('date', flat=True).first()
    )
    default_start = max(start_date, today - timedelta(days=lookback_days))
    if oldest_entry is None:
        oldest_entry = default_start
    else:
        oldest_entry = max(min(oldest_entry, default_start), start_date)

    holiday_dates = set(DeliveryDayStatus.objects.filter(is_holiday=True).values_list('day', flat=True))
    morning_total = Customer.objects.filter(morning_litre__gt=0).count()
    evening_total = Customer.objects.filter(evening_litre__gt=0).count()

    check_day = oldest_entry
    missed_days = []
    while check_day < today:
        if check_day in holiday_dates:
            check_day = check_day.fromordinal(check_day.toordinal() + 1)
            continue
        morning_checked, _ = _shift_counts_for_date(check_day, 'morning')
        evening_checked, _ = _shift_counts_for_date(check_day, 'evening')
        morning_pending = max(morning_total - morning_checked, 0)
        evening_pending = max(evening_total - evening_checked, 0)
        if morning_pending > 0 or evening_pending > 0:
            missed_days.append(
                {
                    'date': check_day,
                    'morning_pending': morning_pending,
                    'evening_pending': evening_pending,
                }
            )
        check_day = check_day.fromordinal(check_day.toordinal() + 1)
    return missed_days


def _group_missed_days_by_month(missed_days):
    month_map = {}
    for item in missed_days:
        day = item['date']
        key = (day.year, day.month)
        bucket = month_map.setdefault(key, {'year': day.year, 'month': day.month, 'days': []})
        bucket['days'].append(day)
    cards = []
    for _, bucket in sorted(month_map.items(), reverse=True):
        days = sorted(bucket['days'])
        cards.append(
            {
                'year': bucket['year'],
                'month': bucket['month'],
                'month_label': f"{month_name(bucket['month'])} {bucket['year']}",
                'start_day': days[0],
                'end_day': days[-1],
                'count': len(days),
            }
        )
    return cards


def home(request):
    setting = BusinessSetting.get_solo()
    if request.method == 'POST':
        form = BusinessSettingForm(request.POST, instance=setting)
        if form.is_valid():
            form.save()
            messages.success(request, 'Milk price updated.')
            return redirect('home')
    else:
        form = BusinessSettingForm(instance=setting)

    stats = Customer.objects.aggregate(
        total_customers=Count('id'),
        total_morning=Sum('morning_litre'),
        total_evening=Sum('evening_litre'),
        total_daily=Sum(F('morning_litre') + F('evening_litre')),
    )
    today = date.today()
    total_cows = Cow.objects.count()
    today_entries = DailyEntry.objects.filter(date=today).select_related('customer')
    month_entries = DailyEntry.objects.filter(date__year=today.year, date__month=today.month)
    feed_sacks_bought = (
        FeedSackPurchase.objects.filter(purchase_date__year=today.year, purchase_date__month=today.month)
        .aggregate(total=Sum('sack_count'))
        .get('total')
        or 0
    )

    snapshot = _delivery_snapshot(today)
    missed_days = _collect_missed_delivery_days(today=today)
    unread_notifications_count = len(missed_days)
    pending_month_cards = _group_missed_days_by_month(missed_days)
    pending_range_start = missed_days[0]['date'] if missed_days else None
    pending_range_end = missed_days[-1]['date'] if missed_days else None

    today_delivered_litre = sum(entry.delivered_litre for entry in today_entries)
    month_delivered_litre = sum(entry.delivered_litre for entry in month_entries)
    estimated_income = month_delivered_litre * setting.milk_rate_per_litre
    pending_payments_count = MonthlyBill.objects.filter(year=today.year, month=today.month, is_paid=False).count()
    month_start = date(today.year, today.month, 1)
    cows_with_deworming = set(
        CowMedicineRecord.objects.filter(medicine_type=CowMedicineRecord.MED_DEWORMING, given_on__gte=month_start)
        .values_list('cow_id', flat=True)
    )
    cows_with_fmd = set(
        CowMedicineRecord.objects.filter(medicine_type=CowMedicineRecord.MED_FMD, given_on__gte=month_start)
        .values_list('cow_id', flat=True)
    )
    all_cow_ids = set(Cow.objects.values_list('id', flat=True))
    cows_medicine_due_count = len(all_cow_ids - (cows_with_deworming & cows_with_fmd))

    context = {
        'milk_rate': setting.milk_rate_per_litre,
        'price_form': form,
        'today': today,
        'total_customers': stats['total_customers'] or 0,
        'total_morning': stats['total_morning'] or Decimal('0.00'),
        'total_evening': stats['total_evening'] or Decimal('0.00'),
        'total_daily': stats['total_daily'] or Decimal('0.00'),
        'total_cows': total_cows,
        'today_delivered_litre': today_delivered_litre,
        'month_delivered_litre': month_delivered_litre,
        'estimated_income': estimated_income,
        'pending_deliveries_total': snapshot['morning_pending_ui'] + snapshot['evening_pending_ui'],
        'show_delivery_alert': unread_notifications_count > 0,
        'unread_notifications_count': unread_notifications_count,
        'pending_month_cards': pending_month_cards,
        'pending_range_start': pending_range_start,
        'pending_range_end': pending_range_end,
        'feed_sacks_bought': feed_sacks_bought,
        'pending_payments_count': pending_payments_count,
        'cows_medicine_due_count': cows_medicine_due_count,
    }
    return render(request, 'dairy/dashboard.html', context)


def delivery_dashboard(request):
    today = date.today()
    snapshot = _delivery_snapshot(today)
    setting = BusinessSetting.get_solo()
    start_date = setting.data_reset_date

    # Generate all months from start_date to today
    all_months = []
    current = start_date
    while current <= today:
        all_months.append(current)
        # Move to next month
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)

    history_year_choices = sorted({m.year for m in all_months}, reverse=True)

    selected_history_year = _safe_int(request.GET.get('history_year'), today.year)
    selected_history_month = _safe_int(request.GET.get('history_month'), today.month)
    not_started = False

    if all_months:
        if selected_history_year not in history_year_choices:
            selected_history_year = history_year_choices[0]
        month_numbers = sorted({m.month for m in all_months if m.year == selected_history_year}, reverse=True)
        if selected_history_month not in month_numbers:
            selected_history_month = month_numbers[0]
        history_month_choices = [(m, month_name(m)) for m in sorted(month_numbers, reverse=True)]
    else:
        selected_history_year = max(today.year, start_date.year)
        selected_history_month = max(today.month, start_date.month) if selected_history_year == start_date.year else 1
        history_year_choices = [selected_history_year]
        history_month_choices = [(selected_history_month, month_name(selected_history_month))]

    selected_month_start = date(selected_history_year, selected_history_month, 1)
    if selected_month_start < start_date:
        selected_history_year = start_date.year
        selected_history_month = start_date.month
        selected_month_start = start_date
        not_started = True

    history_start, history_end = month_bounds(selected_history_year, selected_history_month)
    holiday_dates = set(
        DeliveryDayStatus.objects.filter(day__range=(history_start, history_end), is_holiday=True).values_list(
            'day', flat=True
        )
    )
    history_entries = DailyEntry.objects.filter(date__range=(history_start, history_end))
    day_total_map = {}
    day_check_map = {}
    for entry in history_entries:
        day_total_map[entry.date] = day_total_map.get(entry.date, Decimal('0.00')) + entry.delivered_litre
        state = day_check_map.setdefault(entry.date, {'morning_checked': 0, 'evening_checked': 0})
        if entry.customer.morning_litre > 0 and _is_shift_checked(entry, 'morning'):
            state['morning_checked'] += 1
        if entry.customer.evening_litre > 0 and _is_shift_checked(entry, 'evening'):
            state['evening_checked'] += 1

    morning_total = Customer.objects.filter(morning_litre__gt=0).count()
    evening_total = Customer.objects.filter(evening_litre__gt=0).count()
    missed_days = []
    check_day = history_start
    while check_day <= min(history_end, today):
        day_state = day_check_map.get(check_day, {'morning_checked': 0, 'evening_checked': 0})
        morning_pending = max(morning_total - day_state['morning_checked'], 0)
        evening_pending = max(evening_total - day_state['evening_checked'], 0)
        is_holiday = check_day in holiday_dates
        if is_holiday:
            morning_pending = 0
            evening_pending = 0
        is_missed = (morning_pending > 0 or evening_pending > 0) and not is_holiday
        if is_missed and check_day < today:
            missed_days.append(
                {
                    'date': check_day,
                    'morning_pending': morning_pending,
                    'evening_pending': evening_pending,
                }
            )
        day_check_map[check_day] = {
            'morning_pending': morning_pending,
            'evening_pending': evening_pending,
            'is_missed': is_missed,
            'is_holiday': is_holiday,
        }
        check_day = check_day.fromordinal(check_day.toordinal() + 1)

    missed_days.sort(key=lambda x: x['date'], reverse=True)

    cal = calendar.Calendar(firstweekday=0)
    delivery_history_weeks = []
    for week in cal.monthdatescalendar(selected_history_year, selected_history_month):
        cells = []
        for day in week:
            is_current_month = day.month == selected_history_month
            is_future = day > today
            cells.append(
                {
                    'day': day,
                    'show_day': is_current_month,
                    'litre': day_total_map.get(day, Decimal('0.00')) if is_current_month else None,
                    'is_missed': day_check_map.get(day, {}).get('is_missed', False) if is_current_month else False,
                    'is_holiday': day_check_map.get(day, {}).get('is_holiday', False) if is_current_month else False,
                    'is_future': is_future if is_current_month else False,
                }
            )
        delivery_history_weeks.append(cells)

    context = {
        'today': today,
        'history_year_choices': history_year_choices,
        'history_month_choices': history_month_choices,
        'selected_history_year': selected_history_year,
        'selected_history_month': selected_history_month,
        'delivery_history_weeks': delivery_history_weeks,
        'missed_days_count': len(missed_days),
        'not_started': not_started,
        'start_date': start_date,
        **snapshot,
    }
    return render(request, 'dairy/delivery_dashboard.html', context)


def delivery_notifications(request):
    today = date.today()
    setting = BusinessSetting.get_solo()
    start_date = setting.data_reset_date
    if request.method == 'POST':
        selected_date = request.POST.get('date')
        if selected_date:
            try:
                day = datetime.strptime(selected_date, '%Y-%m-%d').date()
                if day < start_date:
                    messages.error(request, 'Off day can be set only from April 2026 onward.')
                    return redirect('delivery_notifications')
                status, _ = DeliveryDayStatus.objects.get_or_create(day=day, defaults={'is_holiday': False})
                status.is_holiday = True
                status.save(update_fields=['is_holiday'])
                messages.success(request, f'Marked {day.isoformat()} as off day.')
            except ValueError:
                messages.error(request, 'Invalid date for off day update.')
        return redirect('delivery_notifications')

    missed_days = _collect_missed_delivery_days(today=today, start_date=start_date, lookback_days=120)
    missed_days.sort(key=lambda x: x['date'])
    pending_month_cards = _group_missed_days_by_month(missed_days)
    setting = BusinessSetting.get_solo()
    month_start = date(today.year, today.month, 1)
    feed_sacks_bought = (
        FeedSackPurchase.objects.filter(purchase_date__year=today.year, purchase_date__month=today.month)
        .aggregate(total=Sum('sack_count'))
        .get('total')
        or 0
    )
    pending_payments_count = MonthlyBill.objects.filter(year=today.year, month=today.month, is_paid=False).count()
    cows_with_deworming = set(
        CowMedicineRecord.objects.filter(medicine_type=CowMedicineRecord.MED_DEWORMING, given_on__gte=month_start)
        .values_list('cow_id', flat=True)
    )
    cows_with_fmd = set(
        CowMedicineRecord.objects.filter(medicine_type=CowMedicineRecord.MED_FMD, given_on__gte=month_start)
        .values_list('cow_id', flat=True)
    )
    all_cow_ids = set(Cow.objects.values_list('id', flat=True))
    cows_medicine_due_count = len(all_cow_ids - (cows_with_deworming & cows_with_fmd))
    return render(
        request,
        'dairy/delivery_notifications.html',
        {
            'missed_days': missed_days,
            'missed_days_count': len(missed_days),
            'pending_month_cards': pending_month_cards,
            'feed_sacks_bought': feed_sacks_bought,
            'pending_payments_count': pending_payments_count,
            'cows_medicine_due_count': cows_medicine_due_count,
            'milk_rate': setting.milk_rate_per_litre,
        },
    )


def delivery_date_history(request):
    selected_date = _delivery_date_from_request(request)
    mode = request.GET.get('mode', 'morning')
    if mode not in ('morning', 'evening'):
        mode = 'morning'

    day_status, _ = DeliveryDayStatus.objects.get_or_create(day=selected_date, defaults={'is_holiday': False})

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'mark_holiday':
            day_status.is_holiday = True
            day_status.save(update_fields=['is_holiday'])
            messages.success(request, 'Marked as holiday.')
            return redirect(f"{reverse('delivery_date_history')}?date={selected_date.isoformat()}&mode={mode}")
        if action == 'mark_working':
            day_status.is_holiday = False
            day_status.save(update_fields=['is_holiday'])
            messages.success(request, 'Marked as working day.')
            return redirect(f"{reverse('delivery_date_history')}?date={selected_date.isoformat()}&mode={mode}")
        if action == 'mark_all_delivered':
            customers = (
                Customer.objects.filter(morning_litre__gt=0)
                if mode == 'morning'
                else Customer.objects.filter(evening_litre__gt=0)
            )
            for customer in customers:
                entry = get_or_create_daily_entry(customer, selected_date)
                if mode == 'morning':
                    entry.morning_status = DailyEntry.STATUS_DELIVERED
                    entry.morning_litre = customer.morning_litre
                else:
                    entry.evening_status = DailyEntry.STATUS_DELIVERED
                    entry.evening_litre = customer.evening_litre
                entry.save()
            messages.success(request, f'Marked all {mode} deliveries as delivered.')
            return redirect(f"{reverse('delivery_date_history')}?date={selected_date.isoformat()}&mode={mode}")

        mode = request.POST.get('mode', mode)
        entry = get_object_or_404(DailyEntry, pk=request.POST.get('entry_id'))
        status = request.POST.get('status', DailyEntry.STATUS_DELIVERED)
        litre_unit = request.POST.get('litre_unit', 'litre')
        litre = Decimal('0.50') if litre_unit == 'ml' else Decimal(request.POST.get('litre', '0') or '0')
        if mode == 'morning':
            entry.morning_status = status
            entry.morning_litre = litre
        else:
            entry.evening_status = status
            entry.evening_litre = litre
        entry.save()
        messages.success(request, 'Delivery entry updated.')
        return redirect(f"{reverse('delivery_date_history')}?date={selected_date.isoformat()}&mode={mode}")

    customers = (
        Customer.objects.filter(morning_litre__gt=0)
        if mode == 'morning'
        else Customer.objects.filter(evening_litre__gt=0)
    )
    entries = [get_or_create_daily_entry(customer, selected_date) for customer in customers]
    entries = sorted(entries, key=lambda x: x.customer.name.lower())
    rows = []
    for entry in entries:
        default_litre = entry.customer.morning_litre if mode == 'morning' else entry.customer.evening_litre
        litre_raw = entry.morning_litre if mode == 'morning' else entry.evening_litre
        status = entry.morning_status if mode == 'morning' else entry.evening_status
        checked = _is_shift_checked(entry, mode)
        rows.append(
            {
                'entry': entry,
                'customer': entry.customer,
                'litre': litre_raw if checked else default_litre,
                'status': status,
                'checked': checked,
            }
        )

    context = {
        'selected_date': selected_date,
        'mode': mode,
        'rows': rows,
        'is_holiday': day_status.is_holiday,
        'has_pending_in_mode': any(not row['checked'] for row in rows),
    }
    return render(request, 'dairy/delivery_date_history.html', context)


# 1. Customer module

def customer_list(request):
    query = (request.GET.get('q') or '').strip()
    shift = (request.GET.get('shift') or 'all').strip()
    billing = (request.GET.get('billing') or 'all').strip()

    customers = Customer.objects.all()
    if query:
        customers = customers.filter(
            Q(name__icontains=query) | Q(whatsapp_number__icontains=query) | Q(address__icontains=query)
        )

    if shift == 'morning':
        customers = customers.filter(morning_litre__gt=0)
    elif shift == 'evening':
        customers = customers.filter(evening_litre__gt=0)
    if billing == 'pending':
        today = date.today()
        paid_ids = MonthlyBill.objects.filter(year=today.year, month=today.month, is_paid=True).values_list(
            'customer_id', flat=True
        )
        customers = customers.exclude(id__in=paid_ids)
    elif billing == 'paid':
        today = date.today()
        paid_ids = MonthlyBill.objects.filter(year=today.year, month=today.month, is_paid=True).values_list(
            'customer_id', flat=True
        )
        customers = customers.filter(id__in=paid_ids)

    return render(
        request,
        'dairy/customer_list.html',
        {
            'customers': customers,
            'query': query,
            'shift': shift,
            'billing': billing,
        },
    )


def customer_create(request):
    form = CustomerForm(request.POST or None)
    required_headers = ['name', 'whatsapp_number', 'morning_litre', 'evening_litre', 'address']

    if request.method == 'POST' and request.POST.get('mode') == 'bulk':
        upload = request.FILES.get('csv_file')
        if not upload:
            messages.error(request, 'Please upload a CSV file.')
            return redirect('customer_create')

        content = upload.read().decode('utf-8-sig')
        reader = csv.DictReader(io.StringIO(content))
        if not reader.fieldnames:
            messages.error(request, 'CSV file is empty.')
            return redirect('customer_create')

        headers = [h.strip() for h in reader.fieldnames]
        missing = [h for h in required_headers if h not in headers]
        if missing:
            messages.error(request, f'Missing CSV headers: {", ".join(missing)}')
            return redirect('customer_create')

        customers_to_create = []
        row_number = 1
        for row in reader:
            row_number += 1
            name = (row.get('name') or '').strip()
            whatsapp_number = (row.get('whatsapp_number') or '').strip()
            if not name or not whatsapp_number:
                continue
            try:
                morning = Decimal(str(row.get('morning_litre') or '0').strip() or '0')
                evening = Decimal(str(row.get('evening_litre') or '0').strip() or '0')
            except Exception:
                messages.error(request, f'Invalid litre value at CSV row {row_number}.')
                return redirect('customer_create')

            customers_to_create.append(
                Customer(
                    name=name,
                    whatsapp_number=whatsapp_number,
                    morning_litre=morning,
                    evening_litre=evening,
                    address=(row.get('address') or '').strip(),
                )
            )

        if not customers_to_create:
            messages.warning(request, 'No valid customer rows found in CSV.')
            return redirect('customer_create')

        Customer.objects.bulk_create(customers_to_create)
        messages.success(request, f'{len(customers_to_create)} customers imported from CSV.')
        return redirect('customer_list')

    if request.method == 'POST' and form.is_valid():
        customer = form.save(commit=False)
        if request.POST.get('morning_unit') == 'ml':
            customer.morning_litre = Decimal('0.50')
        if request.POST.get('evening_unit') == 'ml':
            customer.evening_litre = Decimal('0.50')
        customer.save()
        messages.success(request, 'Customer added.')
        return redirect('customer_list')
    return render(
        request,
        'dairy/customer_form.html',
        {
            'form': form,
            'title': 'Add Customer',
            'morning_unit': 'litre',
            'evening_unit': 'litre',
            'bulk_headers': required_headers,
        },
    )


def customer_update(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    form = CustomerForm(request.POST or None, instance=customer)
    if request.method == 'POST' and form.is_valid():
        customer = form.save(commit=False)
        if request.POST.get('morning_unit') == 'ml':
            customer.morning_litre = Decimal('0.50')
        if request.POST.get('evening_unit') == 'ml':
            customer.evening_litre = Decimal('0.50')
        customer.save()
        messages.success(request, 'Customer updated.')
        return redirect('customer_list')
    return render(
        request,
        'dairy/customer_form.html',
        {
            'form': form,
            'title': 'Edit Customer',
            'morning_unit': 'ml' if customer.morning_litre == Decimal('0.50') else 'litre',
            'evening_unit': 'ml' if customer.evening_litre == Decimal('0.50') else 'litre',
        },
    )


def customer_delete(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    if request.method == 'POST':
        customer.delete()
        messages.success(request, 'Customer deleted.')
        return redirect('customer_list')
    return render(request, 'dairy/customer_delete.html', {'customer': customer})


# 2. Delivery tracking flow

def _delivery_date_from_request(request):
    date_str = request.GET.get('date') or request.POST.get('date')
    if date_str:
        try:
            return datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return date.today()
    return date.today()


def delivery_mode_start(request, mode):
    if mode not in ('morning', 'evening'):
        return redirect('customer_list')

    selected_date = _delivery_date_from_request(request)
    customers = (
        list(Customer.objects.filter(morning_litre__gt=0))
        if mode == 'morning'
        else list(Customer.objects.filter(evening_litre__gt=0))
    )
    if not customers:
        messages.info(request, 'No customers found. Add customers first.')
        return redirect('customer_create')

    first_unchecked_index = None
    for idx, customer in enumerate(customers):
        entry = get_or_create_daily_entry(customer, selected_date)
        if not _is_shift_checked(entry, mode):
            first_unchecked_index = idx
            break

    if first_unchecked_index is None:
        return redirect(f"{reverse('delivery_summary', kwargs={'mode': mode})}?date={selected_date.isoformat()}")
    return redirect(
        f"{reverse('delivery_mode', kwargs={'mode': mode})}?date={selected_date.isoformat()}&i={first_unchecked_index}"
    )


def delivery_mode(request, mode):
    if mode not in ('morning', 'evening'):
        return redirect('customer_list')

    selected_date = _delivery_date_from_request(request)
    checked, total_count = _shift_counts_for_date(selected_date, mode)
    if total_count > 0 and checked >= total_count:
        return redirect(f"{reverse('delivery_summary', kwargs={'mode': mode})}?date={selected_date.isoformat()}")
    if mode == 'morning':
        customers = list(Customer.objects.filter(morning_litre__gt=0))
    else:
        customers = list(Customer.objects.filter(evening_litre__gt=0))
    total = len(customers)
    try:
        index = max(0, int(request.GET.get('i', 0) or 0))
    except ValueError:
        index = 0

    if index >= total and total > 0:
        return redirect(f"{reverse('delivery_summary', kwargs={'mode': mode})}?date={selected_date.isoformat()}")

    if total == 0:
        messages.info(request, 'No customers found. Add customers first.')
        return redirect('customer_create')

    customer = customers[index]
    entry = get_or_create_daily_entry(customer, selected_date)

    if request.method == 'POST':
        status = request.POST.get('status', DailyEntry.STATUS_DELIVERED)
        litre_unit = request.POST.get('litre_unit', 'litre')
        litre_value = request.POST.get('litre')
        litre = Decimal('0.50') if litre_unit == 'ml' else Decimal(litre_value or '0.00')

        if mode == 'morning':
            entry.morning_status = status
            entry.morning_litre = litre
        else:
            entry.evening_status = status
            entry.evening_litre = litre
        entry.save()

        next_index = index + 1
        if next_index >= total:
            return redirect(f"{reverse('delivery_summary', kwargs={'mode': mode})}?date={selected_date.isoformat()}")
        return redirect(
            f"{reverse('delivery_mode', kwargs={'mode': mode})}?date={selected_date.isoformat()}&i={next_index}"
        )

    default_litre = customer.morning_litre if mode == 'morning' else customer.evening_litre
    saved_litre_raw = entry.morning_litre if mode == 'morning' else entry.evening_litre
    saved_litre = saved_litre_raw if _is_shift_checked(entry, mode) else default_litre

    context = {
        'mode': mode,
        'selected_date': selected_date,
        'customer': customer,
        'index': index,
        'total': total,
        'default_litre': default_litre,
        'saved_litre': saved_litre,
        'saved_unit': 'ml' if saved_litre == Decimal('0.50') else 'litre',
        'prev_link': (
            f"{reverse('delivery_mode', kwargs={'mode': mode})}?date={selected_date.isoformat()}&i={index - 1}"
            if index > 0
            else None
        ),
    }
    return render(request, 'dairy/delivery_flow.html', context)


def delivery_summary(request, mode):
    if mode not in ('morning', 'evening'):
        return redirect('customer_list')

    selected_date = _delivery_date_from_request(request)
    customers = (
        Customer.objects.filter(morning_litre__gt=0)
        if mode == 'morning'
        else Customer.objects.filter(evening_litre__gt=0)
    )
    entries = [get_or_create_daily_entry(customer, selected_date) for customer in customers]
    entries = sorted(entries, key=lambda x: x.customer.name.lower())

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'mark_off_day':
            status, _ = DeliveryDayStatus.objects.get_or_create(day=selected_date, defaults={'is_holiday': False})
            status.is_holiday = True
            status.save(update_fields=['is_holiday'])
            messages.success(request, f'{selected_date.isoformat()} marked as off day.')
            return redirect(f"{reverse('delivery_date_history')}?date={selected_date.isoformat()}&mode={mode}")
        if action == 'mark_all_delivered':
            for customer in customers:
                entry = get_or_create_daily_entry(customer, selected_date)
                if mode == 'morning':
                    entry.morning_litre = customer.morning_litre
                    entry.morning_status = DailyEntry.STATUS_DELIVERED
                else:
                    entry.evening_litre = customer.evening_litre
                    entry.evening_status = DailyEntry.STATUS_DELIVERED
                entry.save()
            messages.success(request, f'All {mode} deliveries marked as delivered.')
            return redirect(f"{reverse('delivery_summary', kwargs={'mode': mode})}?date={selected_date.isoformat()}")

        entry = get_object_or_404(DailyEntry, pk=request.POST.get('entry_id'))
        litre_unit = request.POST.get('litre_unit', 'litre')
        litre = Decimal('0.50') if litre_unit == 'ml' else Decimal(request.POST.get('litre', '0') or '0')
        if mode == 'morning':
            entry.morning_litre = litre
            entry.morning_status = request.POST.get('status', DailyEntry.STATUS_DELIVERED)
        else:
            entry.evening_litre = litre
            entry.evening_status = request.POST.get('status', DailyEntry.STATUS_DELIVERED)
        entry.save()
        messages.success(request, 'Entry updated.')
        return redirect(f"{reverse('delivery_summary', kwargs={'mode': mode})}?date={selected_date.isoformat()}")

    context = {
        'mode': mode,
        'selected_date': selected_date,
        'entries': entries,
        'edit_link': reverse('delivery_mode_start', kwargs={'mode': mode}) + f'?date={selected_date.isoformat()}',
        'has_pending_in_mode': any(not _is_shift_checked(entry, mode) for entry in entries),
    }
    return render(request, 'dairy/delivery_summary.html', context)


# 3 + 4. Billing and customer detail

def customer_detail(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    today = date.today()
    month = _safe_int(request.GET.get('month'), today.month)
    year = _safe_int(request.GET.get('year'), today.year)
    month = min(12, max(1, month))
    month_form = MonthYearForm(initial={'month': month, 'year': year}, current_year=today.year)

    bill = MonthlyBill.build_for_customer(customer, month, year)
    month_label = f'{month_name(month)} {year}'

    if request.method == 'POST' and request.POST.get('action') == 'toggle_paid':
        bill.is_paid = not bill.is_paid
        bill.save()
        messages.success(request, 'Payment status updated.')
        return redirect(reverse('customer_detail', kwargs={'pk': customer.pk}) + f'?month={month}&year={year}')

    reminder_link = None
    if not bill.is_paid:
        reminder_msg = build_reminder_text(customer.name, month_name(month), bill.total_amount)
        reminder_link = whatsapp_link(customer.whatsapp_number, reminder_msg)

    bill_msg = build_bill_text(customer.name, month_label, bill.total_litre, bill.total_days, bill.total_amount)
    send_bill_link = whatsapp_link(customer.whatsapp_number, bill_msg)

    context = {
        'customer': customer,
        'bill': bill,
        'month': month,
        'year': year,
        'month_label': month_label,
        'month_form': month_form,
        'reminder_link': reminder_link,
        'send_bill_link': send_bill_link,
    }
    return render(request, 'dairy/customer_detail.html', context)


# 5. Monthly review page

def monthly_review(request, customer_id):
    customer = get_object_or_404(Customer, pk=customer_id)
    today = date.today()

    month = _safe_int(request.GET.get('month'), today.month)
    year = _safe_int(request.GET.get('year'), today.year)
    month = min(12, max(1, month))

    if request.method == 'POST' and request.POST.get('action') == 'edit_day':
        selected_date = datetime.strptime(request.POST['date'], '%Y-%m-%d').date()
        entry = get_or_create_daily_entry(customer, selected_date)
        post_data = request.POST.copy()
        if request.POST.get('morning_unit') == 'ml':
            post_data['morning_litre'] = '0.50'
        if request.POST.get('evening_unit') == 'ml':
            post_data['evening_litre'] = '0.50'
        form = DailyEntryModalForm(post_data, instance=entry)
        if form.is_valid():
            form.save()
            MonthlyBill.build_for_customer(customer, month, year)
            messages.success(request, f'Updated {selected_date.isoformat()}.')
        return redirect(reverse('monthly_review', kwargs={'customer_id': customer.id}) + f'?month={month}&year={year}')

    start, end = month_bounds(year, month)
    entries_qs = DailyEntry.objects.filter(customer=customer, date__range=(start, end))
    entry_map = {entry.date: entry for entry in entries_qs}

    cal = calendar.Calendar(firstweekday=0)
    weeks = []
    for week in cal.monthdatescalendar(year, month):
        week_cells = []
        for day in week:
            entry = entry_map.get(day)
            is_current_month = day.month == month
            is_future = day > today

            total_litre = Decimal('0.00')
            if entry:
                total_litre = entry.delivered_litre

            if not is_current_month or is_future:
                cell_class = 'cell-muted'
            elif entry and total_litre > 0:
                cell_class = 'cell-delivered'
            elif entry:
                cell_class = 'cell-no-milk'
            else:
                cell_class = 'cell-muted'

            week_cells.append(
                {
                    'day': day,
                    'show_day': is_current_month,
                    'is_current_month': is_current_month,
                    'can_edit': is_current_month and not is_future,
                    'entry': entry,
                    'total_litre': total_litre,
                    'cell_class': cell_class,
                }
            )
        weeks.append(week_cells)

    bill = MonthlyBill.build_for_customer(customer, month, year)

    entry_payload = {}
    for entry in entries_qs:
        amount = compute_entry_amount(entry)
        entry_payload[entry.date.isoformat()] = {
            'morning_litre': str(entry.morning_litre),
            'morning_status': entry.morning_status,
            'evening_litre': str(entry.evening_litre),
            'evening_status': entry.evening_status,
            'amount': str(amount),
            'total_litre': str(entry.delivered_litre),
        }

    prev_month = month - 1
    prev_year = year
    if prev_month == 0:
        prev_month = 12
        prev_year -= 1

    next_month = month + 1
    next_year = year
    if next_month == 13:
        next_month = 1
        next_year += 1

    month_form = MonthYearForm(initial={'month': month, 'year': year}, current_year=today.year)

    month_label = f'{month_name(month)} {year}'
    send_bill_link = whatsapp_link(
        customer.whatsapp_number,
        build_bill_text(customer.name, month_label, bill.total_litre, bill.total_days, bill.total_amount),
    )

    return render(
        request,
        'dairy/monthly_review.html',
        {
            'customer': customer,
            'month': month,
            'year': year,
            'month_label': month_label,
            'weeks': weeks,
            'bill': bill,
            'entry_payload': entry_payload,
            'prev_url': reverse('monthly_review', kwargs={'customer_id': customer.id})
            + f'?month={prev_month}&year={prev_year}',
            'next_url': reverse('monthly_review', kwargs={'customer_id': customer.id})
            + f'?month={next_month}&year={next_year}',
            'month_form': month_form,
            'send_bill_link': send_bill_link,
        },
    )


def _build_feed_sack_day_groups(purchases):
    groups = {}
    for purchase in purchases:
        group = groups.setdefault(
            purchase.purchase_date,
            {
                'purchase_date': purchase.purchase_date,
                'total_sacks': 0,
                'sack_rows': [],
                'cost_rows': [],
                'grand_total_amount': Decimal('0.00'),
            },
        )
        sack_rows = [
            {
                'name': item.sack_name,
                'price': item.price_per_sack,
                'count': item.sack_count,
                'total': item.line_total,
            }
            for item in purchase.items.all()
        ]
        if not sack_rows:
            sack_rows = [
                {
                    'name': 'Feed sack',
                    'price': Decimal('0.00'),
                    'count': purchase.sack_count,
                    'total': Decimal('0.00'),
                }
            ]
        cost_rows = [
            {
                'name': cost.cost_type,
                'amount': cost.amount,
            }
            for cost in purchase.additional_costs.all()
        ]
        group['sack_rows'].extend(sack_rows)
        group['cost_rows'].extend(cost_rows)
        group['total_sacks'] += sum(row['count'] for row in sack_rows)
        group['grand_total_amount'] += sum(row['total'] for row in sack_rows) + sum(row['amount'] for row in cost_rows)
    return list(groups.values())


def feed_sack_list(request):
    today = date.today()
    selected_year = _safe_int(request.GET.get('year'), today.year)
    selected_month = _safe_int(request.GET.get('month'), today.month)
    selected_month = min(12, max(1, selected_month))

    available_months = []
    month_rows = FeedSackPurchase.objects.dates('purchase_date', 'month', order='DESC')
    for month_date in month_rows:
        available_months.append(
            {
                'year': month_date.year,
                'month': month_date.month,
                'label': f'{month_name(month_date.month)} {month_date.year}',
                'url': f'{reverse("feed_sack_list")}?year={month_date.year}&month={month_date.month}',
                'is_selected': month_date.year == selected_year and month_date.month == selected_month,
            }
        )

    if available_months and not any(item['is_selected'] for item in available_months):
        selected_year = available_months[0]['year']
        selected_month = available_months[0]['month']
        available_months[0]['is_selected'] = True

    purchases = (
        FeedSackPurchase.objects.filter(purchase_date__year=selected_year, purchase_date__month=selected_month)
        .prefetch_related('items', 'additional_costs')
        .order_by('-purchase_date', '-id')
    )
    selected_month_label = f'{month_name(selected_month)} {selected_year}'
    return render(
        request,
        'dairy/feed_sack_list.html',
        {
            'purchase_groups': _build_feed_sack_day_groups(purchases),
            'available_months': available_months,
            'selected_month_label': selected_month_label,
        },
    )


def feed_sack_create(request):
    initial = {'purchase_date': date.today().strftime('%d/%m/%Y')}
    form = FeedSackForm(request.POST or None, initial=initial)
    item_errors = []
    cost_errors = []
    if request.method == 'POST' and form.is_valid():
        sack_names = request.POST.getlist('sack_name')
        prices = request.POST.getlist('price_per_sack')
        counts = request.POST.getlist('sack_count')
        cost_types = request.POST.getlist('cost_type')
        cost_amounts = request.POST.getlist('cost_amount')

        item_rows = []
        for index, sack_name in enumerate(sack_names):
            sack_name = sack_name.strip()
            price_value = prices[index].strip() if index < len(prices) else ''
            count_value = counts[index].strip() if index < len(counts) else ''
            if not sack_name and not price_value and not count_value:
                continue
            try:
                price = Decimal(price_value)
                count = int(count_value)
            except (InvalidOperation, ValueError):
                item_errors.append('Please enter a valid price and sack count for every sack row.')
                continue
            if not sack_name or price < 0 or count < 1:
                item_errors.append('Sack name is required, price cannot be negative, and count must be at least 1.')
                continue
            item_rows.append({'sack_name': sack_name, 'price_per_sack': price, 'sack_count': count})

        cost_rows = []
        for index, cost_type in enumerate(cost_types):
            cost_type = cost_type.strip()
            amount_value = cost_amounts[index].strip() if index < len(cost_amounts) else ''
            if not cost_type and not amount_value:
                continue
            try:
                amount = Decimal(amount_value)
            except InvalidOperation:
                cost_errors.append('Please enter a valid amount for every additional price row.')
                continue
            if not cost_type or amount < 0:
                cost_errors.append('Additional price name is required and amount cannot be negative.')
                continue
            cost_rows.append({'cost_type': cost_type, 'amount': amount})

        if not item_rows:
            item_errors.append('Add at least one sack row.')

        if not item_errors and not cost_errors:
            with transaction.atomic():
                purchase_date = form.cleaned_data['purchase_date']
                purchase = FeedSackPurchase.objects.filter(purchase_date=purchase_date).order_by('id').first()
                if purchase is None:
                    purchase = form.save(commit=False)
                    purchase.sack_count = 0
                    purchase.save()
                FeedSackItem.objects.bulk_create(
                    FeedSackItem(purchase=purchase, **row) for row in item_rows
                )
                FeedSackAdditionalCost.objects.bulk_create(
                    FeedSackAdditionalCost(purchase=purchase, **row) for row in cost_rows
                )
                total_sacks = purchase.items.aggregate(total=Sum('sack_count')).get('total') or 0
                purchase.sack_count = total_sacks
                purchase.save(update_fields=['sack_count'])
            messages.success(request, 'Feed sack entry added.')
            return redirect(
                f'{reverse("feed_sack_list")}?year={purchase.purchase_date.year}&month={purchase.purchase_date.month}'
            )
        for error in item_errors + cost_errors:
            messages.error(request, error)
    return render(request, 'dairy/feed_sack_form.html', {'form': form})


# 7. Cow module

def cow_list(request):
    listing_exists = CowMarketplaceListing.objects.filter(cow_id=OuterRef('pk'))
    cows = Cow.objects.select_related('mother').annotate(has_shop_listing=Exists(listing_exists))
    return render(request, 'dairy/cow_list.html', {'cows': cows})


def cow_create(request):
    form = CowForm(request.POST or None, request.FILES or None)
    diseases = DiseaseType.objects.filter(is_active=True)
    available_kids = Cow.objects.all()
    if request.method == 'POST' and form.is_valid():
        cow = form.save()
        selected_ids = [int(k) for k in request.POST.getlist('kid_ids') if k.isdigit()]
        Cow.objects.filter(mother=cow).exclude(id__in=selected_ids).update(mother=None)
        if selected_ids:
            Cow.objects.filter(id__in=selected_ids).update(mother=cow)
        selected_ids = {int(d) for d in request.POST.getlist('given_disease_ids') if d.isdigit()}
        today = date.today()
        for disease in diseases:
            record, _ = CowDiseaseMonthlyStatus.objects.get_or_create(
                cow=cow, disease=disease, month=today.month, year=today.year
            )
            record.is_given = disease.id in selected_ids
            record.save()
        messages.success(request, 'Cow added.')
        return redirect('cow_detail', pk=cow.pk)
    return render(
        request,
        'dairy/cow_form.html',
        {
            'form': form,
            'title': 'Add Cow/Calf',
            'diseases': diseases,
            'selected_disease_ids': set(),
            'available_kids': available_kids,
            'selected_kid_ids': [],
            'disease_add_next': reverse('cow_create'),
        },
    )


def cow_update(request, pk):
    cow = get_object_or_404(Cow, pk=pk)
    form = CowForm(request.POST or None, request.FILES or None, instance=cow)
    diseases = DiseaseType.objects.filter(is_active=True)
    available_kids = Cow.objects.exclude(pk=cow.pk)
    today = date.today()

    if request.method == 'POST' and form.is_valid():
        cow = form.save()
        selected_kid_ids = [int(k) for k in request.POST.getlist('kid_ids') if k.isdigit()]
        Cow.objects.filter(mother=cow).exclude(id__in=selected_kid_ids).update(mother=None)
        if selected_kid_ids:
            Cow.objects.filter(id__in=selected_kid_ids).update(mother=cow)

        selected_ids = {int(d) for d in request.POST.getlist('given_disease_ids') if d.isdigit()}
        for disease in diseases:
            record, _ = CowDiseaseMonthlyStatus.objects.get_or_create(
                cow=cow, disease=disease, month=today.month, year=today.year
            )
            record.is_given = disease.id in selected_ids
            record.save()
        messages.success(request, 'Cow updated.')
        return redirect('cow_detail', pk=cow.pk)

    existing = CowDiseaseMonthlyStatus.objects.filter(cow=cow, month=today.month, year=today.year, is_given=True)
    selected_disease_ids = {obj.disease_id for obj in existing}
    selected_kid_ids = list(cow.children.values_list('id', flat=True))
    return render(
        request,
        'dairy/cow_form.html',
        {
            'form': form,
            'title': 'Edit Cow/Calf',
            'cow': cow,
            'diseases': diseases,
            'selected_disease_ids': selected_disease_ids,
            'available_kids': available_kids,
            'selected_kid_ids': selected_kid_ids,
            'disease_add_next': reverse('cow_update', kwargs={'pk': cow.pk}),
            'current_month_label': today.strftime('%B %Y'),
        },
    )


def cow_detail(request, pk):
    cow = get_object_or_404(Cow.objects.select_related('mother').prefetch_related('children'), pk=pk)
    today = date.today()
    diseases = DiseaseType.objects.filter(is_active=True)
    records = CowDiseaseMonthlyStatus.objects.filter(cow=cow, month=today.month, year=today.year)
    status_map = {record.disease_id: record for record in records}

    disease_rows = []
    for disease in diseases:
        rec = status_map.get(disease.id)
        disease_rows.append(
            {
                'disease': disease,
                'is_given': rec.is_given if rec else False,
            }
        )

    treatment_history = cow.treatment_logs.all()[:20]
    listing = getattr(cow, 'marketplace_listing', None)
    deworming_latest = (
        cow.medicine_records.filter(medicine_type=CowMedicineRecord.MED_DEWORMING).order_by('-given_on', '-id').first()
    )
    fmd_latest = cow.medicine_records.filter(medicine_type=CowMedicineRecord.MED_FMD).order_by('-given_on', '-id').first()

    return render(
        request,
        'dairy/cow_detail.html',
        {
            'cow': cow,
            'disease_rows': disease_rows,
            'current_month_label': today.strftime('%B %Y'),
            'treatment_history': treatment_history,
            'listing': listing,
            'deworming_latest': deworming_latest,
            'fmd_latest': fmd_latest,
        },
    )


def disease_create(request):
    form = DiseaseTypeForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Disease added.')
        next_url = request.GET.get('next')
        if next_url:
            return redirect(next_url)
        return redirect('home')
    return render(request, 'dairy/disease_form.html', {'form': form})


def marketplace_list(request):
    listings = CowMarketplaceListing.objects.filter(is_active=True).select_related('cow', 'cow__mother')
    return render(request, 'dairy/marketplace_list.html', {'listings': listings})


def cow_health(request, pk):
    cow = get_object_or_404(Cow, pk=pk)
    form = CowTreatmentLogForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        obj = form.save(commit=False)
        obj.cow = cow
        obj.save()
        messages.success(request, 'Treatment record saved.')
        return redirect('cow_health', pk=cow.pk)
    history = cow.treatment_logs.all()[:30]
    return render(request, 'dairy/cow_health.html', {'cow': cow, 'form': form, 'history': history})


def cow_sell(request, pk):
    cow = get_object_or_404(Cow.objects.select_related('mother').prefetch_related('children'), pk=pk)
    listing_instance = getattr(cow, 'marketplace_listing', None)
    form = CowMarketplaceListingForm(request.POST or None, instance=listing_instance)
    if request.method == 'POST' and form.is_valid():
        listing = form.save(commit=False)
        listing.cow = cow
        listing.is_active = True
        listing.sold_on = None
        if not listing.pk:
            listing.listed_on = date.today()
        listing.save()
        messages.success(request, 'Cow published to marketplace.')
        return redirect('home')
    return render(request, 'dairy/cow_sell.html', {'cow': cow, 'form': form, 'listing': listing_instance})


def cow_shop_record(request, pk):
    cow = get_object_or_404(Cow.objects.select_related('mother').prefetch_related('children'), pk=pk)
    listing = get_object_or_404(CowMarketplaceListing, cow=cow)

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'sold_out':
            listing.is_active = False
            listing.sold_on = date.today()
            listing.save(update_fields=['is_active', 'sold_on'])
            messages.success(request, 'Marked as sold out and removed from shop.')
            return redirect('marketplace_list')
        if action == 'cancel_listing':
            listing.is_active = False
            listing.sold_on = None
            listing.save(update_fields=['is_active', 'sold_on'])
            messages.success(request, 'Listing canceled and removed from shop.')
            return redirect('marketplace_list')

    return render(request, 'dairy/cow_shop_record.html', {'cow': cow, 'listing': listing})


def marketplace_cow_detail(request, pk):
    cow = get_object_or_404(Cow.objects.select_related('mother').prefetch_related('children'), pk=pk)
    listing = get_object_or_404(CowMarketplaceListing, cow=cow, is_active=True)
    deworming_latest = (
        cow.medicine_records.filter(medicine_type=CowMedicineRecord.MED_DEWORMING).order_by('-given_on', '-id').first()
    )
    fmd_latest = cow.medicine_records.filter(medicine_type=CowMedicineRecord.MED_FMD).order_by('-given_on', '-id').first()
    return render(
        request,
        'dairy/marketplace_cow_detail.html',
        {
            'cow': cow,
            'listing': listing,
            'deworming_latest': deworming_latest,
            'fmd_latest': fmd_latest,
        },
    )


def cow_medicine_edit(request, pk):
    cow = get_object_or_404(Cow, pk=pk)
    deworming_form = CowMedicineRecordForm(
        request.POST or None,
        prefix='deworming',
        initial={'given_on': date.today()},
    )
    fmd_form = CowMedicineRecordForm(
        request.POST or None,
        prefix='fmd',
        initial={'given_on': date.today()},
    )

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add_deworming' and deworming_form.is_valid():
            rec = deworming_form.save(commit=False)
            rec.cow = cow
            rec.medicine_type = CowMedicineRecord.MED_DEWORMING
            rec.save()
            messages.success(request, 'Deworming record saved.')
            return redirect('cow_medicine_edit', pk=cow.pk)
        if action == 'add_fmd' and fmd_form.is_valid():
            rec = fmd_form.save(commit=False)
            rec.cow = cow
            rec.medicine_type = CowMedicineRecord.MED_FMD
            rec.save()
            messages.success(request, 'FMD vaccine record saved.')
            return redirect('cow_medicine_edit', pk=cow.pk)
        if action == 'delete_record':
            rec = get_object_or_404(CowMedicineRecord, pk=request.POST.get('record_id'), cow=cow)
            rec.delete()
            messages.success(request, 'Medicine record deleted.')
            return redirect('cow_medicine_edit', pk=cow.pk)
        if action == 'clear_history':
            med_type = request.POST.get('medicine_type')
            if med_type in (CowMedicineRecord.MED_DEWORMING, CowMedicineRecord.MED_FMD):
                cow.medicine_records.filter(medicine_type=med_type).delete()
                messages.success(request, 'Medicine history cleared.')
            return redirect('cow_medicine_edit', pk=cow.pk)

    deworming_records = cow.medicine_records.filter(medicine_type=CowMedicineRecord.MED_DEWORMING).order_by('-given_on', '-id')
    fmd_records = cow.medicine_records.filter(medicine_type=CowMedicineRecord.MED_FMD).order_by('-given_on', '-id')
    return render(
        request,
        'dairy/cow_medicine_edit.html',
        {
            'cow': cow,
            'deworming_form': deworming_form,
            'fmd_form': fmd_form,
            'deworming_records': deworming_records,
            'fmd_records': fmd_records,
        },
    )




def cow_medicine_history(request, pk, medicine_type):
    cow = get_object_or_404(Cow, pk=pk)
    if medicine_type not in (CowMedicineRecord.MED_DEWORMING, CowMedicineRecord.MED_FMD):
        return redirect('cow_detail', pk=cow.pk)
    records = cow.medicine_records.filter(medicine_type=medicine_type).order_by('given_on', 'created_at', 'id')
    title = 'Deworming' if medicine_type == CowMedicineRecord.MED_DEWORMING else 'FMD Vaccine'
    return render(
        request,
        'dairy/cow_medicine_history.html',
        {'cow': cow, 'records': records, 'medicine_type': medicine_type, 'title': title},
    )


def settings(request):
    return render(request, 'dairy/settings.html')


def reset_data(request):
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'confirm_reset':
            # Clear all data
            DailyEntry.objects.all().delete()
            Customer.objects.all().delete()
            Cow.objects.all().delete()
            MonthlyBill.objects.all().delete()
            FeedSackPurchase.objects.all().delete()
            CowMedicineRecord.objects.all().delete()
            CowTreatmentLog.objects.all().delete()
            CowDiseaseMonthlyStatus.objects.all().delete()
            DeliveryDayStatus.objects.all().delete()

            # Reset settings
            setting = BusinessSetting.get_solo()
            setting.data_reset_date = date.today()
            setting.milk_rate_per_litre = Decimal('0.00')
            setting.save()

            messages.success(request, 'All data has been cleared. The app is reset.')
            return redirect('home')

    return render(request, 'dairy/reset_confirm.html')

