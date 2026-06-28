from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q, Sum


class Customer(models.Model):
    name = models.CharField(max_length=120)
    whatsapp_number = models.CharField(max_length=20)
    morning_litre = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('0.00'))
    evening_litre = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('0.00'))
    address = models.TextField(blank=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class BusinessSetting(models.Model):
    milk_rate_per_litre = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('60.00'))
    data_reset_date = models.DateField(default=date(2026, 4, 1))
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Rate ₹{self.milk_rate_per_litre}/L'

    @classmethod
    def get_solo(cls):
        setting, _ = cls.objects.get_or_create(pk=1)
        return setting


class DailyEntry(models.Model):
    STATUS_DELIVERED = 'delivered'
    STATUS_NO_MILK = 'no_milk'
    STATUS_CHOICES = [
        (STATUS_DELIVERED, 'Delivered'),
        (STATUS_NO_MILK, 'No Milk'),
    ]

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='daily_entries')
    date = models.DateField(default=date.today)
    morning_litre = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('0.00'))
    evening_litre = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('0.00'))
    morning_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DELIVERED)
    evening_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DELIVERED)

    class Meta:
        unique_together = ('customer', 'date')
        ordering = ['-date', 'customer__name']

    def __str__(self):
        return f'{self.customer.name} - {self.date}'

    @property
    def delivered_litre(self):
        total = Decimal('0.00')
        if self.morning_status == self.STATUS_DELIVERED:
            total += self.morning_litre
        if self.evening_status == self.STATUS_DELIVERED:
            total += self.evening_litre
        return total


class DeliveryDayStatus(models.Model):
    day = models.DateField(unique=True)
    is_holiday = models.BooleanField(default=False)

    class Meta:
        ordering = ['-day']

    def __str__(self):
        return f'{self.day} - {"Holiday" if self.is_holiday else "Working"}'


class MonthlyBill(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='monthly_bills')
    month = models.PositiveSmallIntegerField()
    year = models.PositiveSmallIntegerField()
    total_litre = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    total_days = models.PositiveIntegerField(default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    is_paid = models.BooleanField(default=False)

    class Meta:
        unique_together = ('customer', 'month', 'year')
        ordering = ['-year', '-month', 'customer__name']

    def __str__(self):
        return f'{self.customer.name} - {self.month}/{self.year}'

    @classmethod
    def build_for_customer(cls, customer, month, year):
        entries = DailyEntry.objects.filter(customer=customer, date__month=month, date__year=year)
        total_litre = Decimal('0.00')
        total_days = 0

        for entry in entries:
            litre = entry.delivered_litre
            if litre > 0:
                total_days += 1
            total_litre += litre

        rate = BusinessSetting.get_solo().milk_rate_per_litre
        total_amount = total_litre * rate

        bill, _ = cls.objects.get_or_create(customer=customer, month=month, year=year)
        bill.total_litre = total_litre
        bill.total_days = total_days
        bill.total_amount = total_amount
        bill.save()
        return bill


class Cow(models.Model):
    SEX_MALE = 'male'
    SEX_FEMALE = 'female'
    SEX_CHOICES = [
        (SEX_MALE, 'Male'),
        (SEX_FEMALE, 'Female'),
    ]

    photo = models.ImageField(upload_to='cows/', blank=True, null=True)
    name = models.CharField(max_length=100)
    ear_tag_number = models.CharField(max_length=60, blank=True)
    age = models.PositiveIntegerField(help_text='Age in years')
    sex = models.CharField(max_length=10, choices=SEX_CHOICES)
    number_of_pregnancy = models.PositiveIntegerField(blank=True, null=True)
    currently_pregnant = models.BooleanField(default=False)
    average_litre_per_day = models.DecimalField(max_digits=6, decimal_places=2, blank=True, null=True)
    medicine = models.CharField(max_length=255, blank=True)
    injection = models.CharField(max_length=255, blank=True)
    mother = models.ForeignKey('self', on_delete=models.SET_NULL, blank=True, null=True, related_name='children')
    is_bought = models.BooleanField(default=False)
    birth_date = models.DateField(blank=True, null=True)
    buyed_date = models.DateField(blank=True, null=True)

    class Meta:
        ordering = ['name']
        constraints = [
            models.CheckConstraint(condition=~Q(pk=models.F('mother_id')), name='cow_not_own_mother'),
        ]

    def __str__(self):
        return self.name

    def clean(self):
        if self.sex == self.SEX_MALE:
            self.number_of_pregnancy = None
            self.currently_pregnant = False
            self.average_litre_per_day = None
        if self.mother_id and self.mother_id == self.id:
            raise ValidationError({'mother': 'A cow cannot be selected as its own mother.'})


class CowMonthlyProduction(models.Model):
    cow = models.ForeignKey(Cow, on_delete=models.CASCADE, related_name='monthly_productions')
    month = models.PositiveSmallIntegerField()
    year = models.PositiveSmallIntegerField()
    total_litre = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    avg_litre_per_day = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('0.00'))

    class Meta:
        unique_together = ('cow', 'month', 'year')
        ordering = ['-year', '-month']

    def __str__(self):
        return f'{self.cow.name} {self.month}/{self.year} - {self.total_litre}L'


class CowTreatmentLog(models.Model):
    cow = models.ForeignKey(Cow, on_delete=models.CASCADE, related_name='treatment_logs')
    disease_name = models.CharField(max_length=120)
    treatment = models.CharField(max_length=180, blank=True)
    medicine_given = models.CharField(max_length=180, blank=True)
    checkup_date = models.DateField(default=date.today)
    worm_medicine = models.BooleanField(default=False)
    monthly_checkup = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    treated_by = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ['-checkup_date', '-id']

    def __str__(self):
        return f'{self.cow.name} - {self.disease_name} ({self.checkup_date})'


class CowMedicineRecord(models.Model):
    MED_DEWORMING = 'deworming'
    MED_FMD = 'fmd_vaccine'
    MEDICINE_CHOICES = [
        (MED_DEWORMING, 'Deworming'),
        (MED_FMD, 'FMD Vaccine'),
    ]

    cow = models.ForeignKey(Cow, on_delete=models.CASCADE, related_name='medicine_records')
    medicine_type = models.CharField(max_length=20, choices=MEDICINE_CHOICES)
    given_on = models.DateField(default=date.today)
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['given_on', 'created_at']

    def __str__(self):
        return f'{self.cow.name} - {self.get_medicine_type_display()} ({self.given_on})'


class CowMarketplaceListing(models.Model):
    cow = models.OneToOneField(Cow, on_delete=models.CASCADE, related_name='marketplace_listing')
    selling_price = models.DecimalField(max_digits=12, decimal_places=2)
    is_active = models.BooleanField(default=True)
    listed_on = models.DateField(default=date.today)
    sold_on = models.DateField(blank=True, null=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-listed_on', '-id']

    def __str__(self):
        return f'{self.cow.name} - Rs {self.selling_price}'


class FeedSackPurchase(models.Model):
    purchase_date = models.DateField(default=date.today)
    sack_count = models.PositiveIntegerField(default=1)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['-purchase_date', '-id']

    def __str__(self):
        return f'{self.purchase_date} - {self.total_sacks} sacks'

    @property
    def total_sacks(self):
        lines = getattr(self, '_prefetched_objects_cache', {}).get('items')
        if lines is not None:
            total = sum(item.sack_count for item in lines)
            return total or self.sack_count
        total = self.items.aggregate(total=Sum('sack_count')).get('total') or 0
        return total or self.sack_count

    @property
    def sack_total_amount(self):
        lines = getattr(self, '_prefetched_objects_cache', {}).get('items')
        if lines is not None:
            return sum(item.line_total for item in lines)
        return sum(item.line_total for item in self.items.all())

    @property
    def additional_total_amount(self):
        costs = getattr(self, '_prefetched_objects_cache', {}).get('additional_costs')
        if costs is not None:
            return sum(cost.amount for cost in costs)
        return sum(cost.amount for cost in self.additional_costs.all())

    @property
    def grand_total_amount(self):
        return self.sack_total_amount + self.additional_total_amount


class FeedSackItem(models.Model):
    purchase = models.ForeignKey(FeedSackPurchase, on_delete=models.CASCADE, related_name='items')
    sack_name = models.CharField(max_length=120)
    price_per_sack = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    sack_count = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f'{self.sack_name} - {self.sack_count} sacks'

    @property
    def line_total(self):
        return self.price_per_sack * self.sack_count


class FeedSackAdditionalCost(models.Model):
    purchase = models.ForeignKey(FeedSackPurchase, on_delete=models.CASCADE, related_name='additional_costs')
    cost_type = models.CharField(max_length=120)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f'{self.cost_type} - {self.amount}'


class DiseaseType(models.Model):
    name = models.CharField(max_length=120, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class CowDiseaseMonthlyStatus(models.Model):
    cow = models.ForeignKey(Cow, on_delete=models.CASCADE, related_name='disease_statuses')
    disease = models.ForeignKey(DiseaseType, on_delete=models.CASCADE, related_name='cow_statuses')
    month = models.PositiveSmallIntegerField()
    year = models.PositiveSmallIntegerField()
    is_given = models.BooleanField(default=False)

    class Meta:
        unique_together = ('cow', 'disease', 'month', 'year')
        ordering = ['-year', '-month', 'disease__name']

    def __str__(self):
        return f'{self.cow.name} - {self.disease.name} ({self.month}/{self.year})'
