from django.contrib.auth.forms import UserCreationForm
from django import forms
from .constants import ACCOUNT_TYPE, GENDER_TYPE
from django.contrib.auth.models import User
from .models import UserBankAccount, UserAddress

class UserRegistrationForm(UserCreationForm):
    """
    Extends Django's UserCreationForm to collect additional
    profile and account details, then creates related
    UserAddress and UserBankAccount records on save.
    """
    birth_date = forms.DateField(widget=forms.DateInput(attrs={'type':'date'}))
    gender = forms.ChoiceField(choices=GENDER_TYPE)
    account_type = forms.ChoiceField(choices=ACCOUNT_TYPE)
    street_address = forms.CharField(max_length=100)
    city = forms.CharField(max_length=100)
    postal_code = forms.IntegerField()
    country = forms.CharField(max_length=100)

    class Meta:
        model = User
        fields = [
            'username', 'password1', 'password2',
            'first_name', 'last_name', 'email',
            'account_type', 'birth_date', 'gender',
            'postal_code', 'city', 'country', 'street_address'
        ]

    def save(self, commit=True):
        """
        Save the User first, then create associated
        UserAddress and UserBankAccount instances.
        """
        our_user = super().save(commit=False)
        if commit:
            # Save the core User object
            our_user.save()
            # Extract form data for related models
            account_type = self.cleaned_data['account_type']
            gender = self.cleaned_data['gender']
            postal_code = self.cleaned_data['postal_code']
            country = self.cleaned_data['country']
            birth_date = self.cleaned_data['birth_date']
            city = self.cleaned_data['city']
            street_address = self.cleaned_data['street_address']

            # Create address record
            UserAddress.objects.create(
                user=our_user,
                postal_code=postal_code,
                country=country,
                city=city,
                street_address=street_address
            )
            # Create bank account record
            UserBankAccount.objects.create(
                user=our_user,
                account_type=account_type,
                gender=gender,
                birth_date=birth_date,
                account_no=100000 + our_user.id
            )
        return our_user

    def __init__(self, *args, **kwargs):
        """
        Add a CSS class to each field for consistent styling.
        """
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({
                'class': (
                    'appearance-none block w-full bg-gray-200 '
                    'text-gray-700 border border-gray-200 rounded '
                    'py-3 px-4 leading-tight focus:outline-none '
                    'focus:bg-white focus:border-gray-500'
                )
            })

class UserUpdateForm(forms.ModelForm):
    """
    Allows updating User's basic info plus related
    address and bank account fields in one form.
    """
    birth_date = forms.DateField(widget=forms.DateInput(attrs={'type':'date'}))
    gender = forms.ChoiceField(choices=GENDER_TYPE)
    account_type = forms.ChoiceField(choices=ACCOUNT_TYPE)
    street_address = forms.CharField(max_length=100)
    city = forms.CharField(max_length=100)
    postal_code = forms.IntegerField()
    country = forms.CharField(max_length=100)

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email']

    def __init__(self, *args, **kwargs):
        """
        Pre-populate form fields with existing User,
        UserBankAccount, and UserAddress data.
        """
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({
                'class': (
                    'appearance-none block w-full bg-gray-200 '
                    'text-gray-700 border border-gray-200 rounded '
                    'py-3 px-4 leading-tight focus:outline-none '
                    'focus:bg-white focus:border-gray-500'
                )
            })
        # Attempt to load related models for initial values
        if self.instance:
            try:
                user_account = self.instance.account
                user_address = self.instance.address
            except UserBankAccount.DoesNotExist:
                user_account = None
                user_address = None
            if user_account and user_address:
                self.fields['account_type'].initial = user_account.account_type
                self.fields['gender'].initial = user_account.gender
                self.fields['birth_date'].initial = user_account.birth_date
                self.fields['street_address'].initial = user_address.street_address
                self.fields['city'].initial = user_address.city
                self.fields['postal_code'].initial = user_address.postal_code
                self.fields['country'].initial = user_address.country

    def save(self, commit=True):
        """
        Save User, then update or create related
        UserBankAccount and UserAddress records.
        """
        user = super().save(commit=False)
        if commit:
            user.save()
            # Get or create related objects
            user_account, _ = UserBankAccount.objects.get_or_create(user=user)
            user_address, _ = UserAddress.objects.get_or_create(user=user)
            # Update from form data
            user_account.account_type = self.cleaned_data['account_type']
            user_account.gender = self.cleaned_data['gender']
            user_account.birth_date = self.cleaned_data['birth_date']
            user_account.save()

            user_address.street_address = self.cleaned_data['street_address']
            user_address.city = self.cleaned_data['city']
            user_address.postal_code = self.cleaned_data['postal_code']
            user_address.country = self.cleaned_data['country']
            user_address.save()
        return user
