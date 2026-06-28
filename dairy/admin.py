from django.contrib import admin

from .models import (
    BusinessSetting,
    Cow,
    CowMedicineRecord,
    CowMarketplaceListing,
    CowDiseaseMonthlyStatus,
    CowMonthlyProduction,
    CowTreatmentLog,
    Customer,
    DailyEntry,
    DiseaseType,
    FeedSackAdditionalCost,
    FeedSackItem,
    FeedSackPurchase,
    MonthlyBill,
)


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('name', 'whatsapp_number', 'morning_litre', 'evening_litre')
    search_fields = ('name', 'whatsapp_number')


@admin.register(DailyEntry)
class DailyEntryAdmin(admin.ModelAdmin):
    list_display = ('customer', 'date', 'morning_status', 'evening_status', 'morning_litre', 'evening_litre')
    list_filter = ('date', 'morning_status', 'evening_status')
    search_fields = ('customer__name',)


@admin.register(MonthlyBill)
class MonthlyBillAdmin(admin.ModelAdmin):
    list_display = ('customer', 'month', 'year', 'total_litre', 'total_days', 'total_amount', 'is_paid')
    list_filter = ('year', 'month', 'is_paid')
    search_fields = ('customer__name',)


@admin.register(Cow)
class CowAdmin(admin.ModelAdmin):
    list_display = ('name', 'sex', 'age', 'average_litre_per_day', 'is_bought', 'mother')
    list_filter = ('sex', 'is_bought')
    search_fields = ('name',)


class FeedSackItemInline(admin.TabularInline):
    model = FeedSackItem
    extra = 0


class FeedSackAdditionalCostInline(admin.TabularInline):
    model = FeedSackAdditionalCost
    extra = 0


@admin.register(FeedSackPurchase)
class FeedSackPurchaseAdmin(admin.ModelAdmin):
    list_display = ('purchase_date', 'sack_count', 'notes')
    list_filter = ('purchase_date',)
    search_fields = ('notes',)
    inlines = [FeedSackItemInline, FeedSackAdditionalCostInline]


@admin.register(BusinessSetting)
class BusinessSettingAdmin(admin.ModelAdmin):
    list_display = ('milk_rate_per_litre', 'updated_at')


@admin.register(DiseaseType)
class DiseaseTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name',)


@admin.register(CowDiseaseMonthlyStatus)
class CowDiseaseMonthlyStatusAdmin(admin.ModelAdmin):
    list_display = ('cow', 'disease', 'month', 'year', 'is_given')
    list_filter = ('year', 'month', 'is_given')
    search_fields = ('cow__name', 'disease__name')


@admin.register(CowMonthlyProduction)
class CowMonthlyProductionAdmin(admin.ModelAdmin):
    list_display = ('cow', 'month', 'year', 'total_litre', 'avg_litre_per_day')
    list_filter = ('year', 'month')
    search_fields = ('cow__name',)


@admin.register(CowTreatmentLog)
class CowTreatmentLogAdmin(admin.ModelAdmin):
    list_display = ('cow', 'disease_name', 'medicine_given', 'checkup_date', 'worm_medicine', 'monthly_checkup')
    list_filter = ('checkup_date', 'worm_medicine', 'monthly_checkup')
    search_fields = ('cow__name', 'disease_name', 'medicine_given', 'treated_by')


@admin.register(CowMarketplaceListing)
class CowMarketplaceListingAdmin(admin.ModelAdmin):
    list_display = ('cow', 'selling_price', 'is_active', 'listed_on', 'sold_on')
    list_filter = ('is_active', 'listed_on')
    search_fields = ('cow__name',)


@admin.register(CowMedicineRecord)
class CowMedicineRecordAdmin(admin.ModelAdmin):
    list_display = ('cow', 'medicine_type', 'given_on', 'note')
    list_filter = ('medicine_type', 'given_on')
    search_fields = ('cow__name', 'note')
