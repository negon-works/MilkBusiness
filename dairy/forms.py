from datetime import date

from django import forms

from .models import (
    BusinessSetting,
    Cow,
    CowMedicineRecord,
    CowMarketplaceListing,
    CowMonthlyProduction,
    CowTreatmentLog,
    Customer,
    DailyEntry,
    DiseaseType,
    FeedSackPurchase,
)


class DateInput(forms.DateInput):
    input_type = 'date'


def apply_tailwind_classes(form):
    for field in form.fields.values():
        widget = field.widget
        css = 'w-full rounded-lg border border-slate-300 px-3 py-2'
        if isinstance(widget, forms.CheckboxInput):
            widget.attrs.update({'class': 'h-4 w-4 rounded border-slate-300'})
        elif isinstance(widget, forms.SelectMultiple):
            widget.attrs.update({'class': css, 'size': widget.attrs.get('size', 5)})
        else:
            existing = widget.attrs.get('class', '')
            widget.attrs['class'] = f'{existing} {css}'.strip()


class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = ['name', 'whatsapp_number', 'morning_litre', 'evening_litre', 'address']
        widgets = {
            'morning_litre': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'evening_litre': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'address': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_tailwind_classes(self)


class DailyEntryModalForm(forms.ModelForm):
    class Meta:
        model = DailyEntry
        fields = ['morning_litre', 'morning_status', 'evening_litre', 'evening_status']
        widgets = {
            'morning_litre': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'evening_litre': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_tailwind_classes(self)


class MonthYearForm(forms.Form):
    month = forms.TypedChoiceField(coerce=int)
    year = forms.TypedChoiceField(coerce=int)

    def __init__(self, *args, **kwargs):
        current_year = kwargs.pop('current_year', date.today().year)
        super().__init__(*args, **kwargs)
        self.fields['month'].choices = [(m, date(2000, m, 1).strftime('%B')) for m in range(1, 13)]
        self.fields['year'].choices = [(y, y) for y in range(current_year - 4, current_year + 3)]
        apply_tailwind_classes(self)


class CowForm(forms.ModelForm):
    class Meta:
        model = Cow
        fields = [
            'photo',
            'name',
            'ear_tag_number',
            'age',
            'sex',
            'number_of_pregnancy',
            'currently_pregnant',
            'average_litre_per_day',
            'mother',
            'is_bought',
            'birth_date',
            'buyed_date',
        ]
        widgets = {
            'birth_date': DateInput(),
            'buyed_date': DateInput(),
            'average_litre_per_day': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['mother'].queryset = Cow.objects.all()
        self.fields['mother'].required = False
        if self.instance and self.instance.pk:
            self.fields['mother'].queryset = Cow.objects.exclude(pk=self.instance.pk)
        apply_tailwind_classes(self)


class BusinessSettingForm(forms.ModelForm):
    class Meta:
        model = BusinessSetting
        fields = ['milk_rate_per_litre']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['milk_rate_per_litre'].widget.attrs.update({'step': '0.01', 'min': '0'})
        apply_tailwind_classes(self)


class FeedSackForm(forms.ModelForm):
    class Meta:
        model = FeedSackPurchase
        fields = ['purchase_date', 'sack_count', 'notes']
        widgets = {
            'purchase_date': DateInput(),
            'sack_count': forms.NumberInput(attrs={'min': '1'}),
            'notes': forms.TextInput(attrs={'placeholder': 'Optional note'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_tailwind_classes(self)


class DiseaseTypeForm(forms.ModelForm):
    class Meta:
        model = DiseaseType
        fields = ['name']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_tailwind_classes(self)


class CowMonthlyProductionForm(forms.ModelForm):
    class Meta:
        model = CowMonthlyProduction
        fields = ['month', 'year', 'total_litre', 'avg_litre_per_day']
        widgets = {
            'month': forms.NumberInput(attrs={'min': '1', 'max': '12'}),
            'year': forms.NumberInput(attrs={'min': '2020'}),
            'total_litre': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'avg_litre_per_day': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_tailwind_classes(self)


class CowTreatmentLogForm(forms.ModelForm):
    class Meta:
        model = CowTreatmentLog
        fields = [
            'disease_name',
            'treatment',
            'medicine_given',
            'checkup_date',
            'worm_medicine',
            'monthly_checkup',
            'treated_by',
            'notes',
        ]
        widgets = {
            'checkup_date': DateInput(),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_tailwind_classes(self)


class CowMarketplaceListingForm(forms.ModelForm):
    class Meta:
        model = CowMarketplaceListing
        fields = ['selling_price', 'is_active', 'notes']
        widgets = {
            'selling_price': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_tailwind_classes(self)


class CowMedicineRecordForm(forms.ModelForm):
    class Meta:
        model = CowMedicineRecord
        fields = ['given_on', 'note']
        widgets = {
            'given_on': DateInput(),
            'note': forms.TextInput(attrs={'placeholder': 'Optional note'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_tailwind_classes(self)
