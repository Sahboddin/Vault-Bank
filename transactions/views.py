from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import CreateView, ListView, FormView
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.core.mail import EmailMultiAlternatives
from django.db.models import Sum
from datetime import datetime

from transactions.constants import DEPOSIT, WITHDRAWAL, LOAN, LOAN_PAID
from transactions.forms import DepositForm, WithdrawForm, LoanRequestForm, TransactionForm
from transactions.models import Transaction
from accounts.models import UserBankAccount

def send_transaction_email(user, amount, subject, template):
    """
    Renders an HTML email template with user and amount, then sends it.
    """
    message = render_to_string(template, {'user': user, 'amount': amount})
    email = EmailMultiAlternatives(subject, '', to=[user.email])
    email.attach_alternative(message, 'text/html')
    email.send()

class TransactionCreateMixin(LoginRequiredMixin, CreateView):
    """
    Mixin that sets up the form to include the user's account,
    applies a common template, and redirects to the report on success.
    """
    template_name = 'transactions/transaction_form.html'
    model = Transaction
    title = ''
    success_url = reverse_lazy('transaction_report')

    def get_form_kwargs(self):
        """Include the current user's account in form kwargs."""
        kwargs = super().get_form_kwargs()
        kwargs['account'] = self.request.user.account
        return kwargs

    def get_context_data(self, **kwargs):
        """Pass the view's title into the template context."""
        context = super().get_context_data(**kwargs)
        context['title'] = self.title
        return context

class DepositMoneyView(TransactionCreateMixin):
    """Handles creating a deposit transaction and updating the user's balance."""
    form_class = DepositForm
    title = 'Deposit'

    def get_initial(self):
        return {'transaction_type': DEPOSIT}

    def form_valid(self, form):
        # Update balance and send notification
        amount = form.cleaned_data['amount']
        account = self.request.user.account
        account.balance += amount
        account.save(update_fields=['balance'])

        messages.success(self.request, f'{amount:,.2f}$ deposited successfully')
        send_transaction_email(self.request.user, amount, 'Deposit Message', 'transactions/deposit_email.html')
        return super().form_valid(form)

class WithdrawMoneyView(TransactionCreateMixin):
    """Handles creating a withdrawal transaction and updating the user's balance."""
    form_class = WithdrawForm
    title = 'Withdraw Money'

    def get_initial(self):
        return {'transaction_type': WITHDRAWAL}

    def form_valid(self, form):
        amount = form.cleaned_data['amount']
        account = self.request.user.account
        account.balance -= amount
        account.save(update_fields=['balance'])

        messages.success(self.request, f'{amount:,.2f}$ withdrawn successfully')
        send_transaction_email(self.request.user, amount, 'Withdrawal Message', 'transactions/withdrawal_email.html')
        return super().form_valid(form)

class LoanRequestView(TransactionCreateMixin):
    """Handles loan requests, enforcing a maximum of 3 active approved loans."""
    form_class = LoanRequestForm
    title = 'Request For Loan'

    def get_initial(self):
        return {'transaction_type': LOAN}

    def form_valid(self, form):
        amount = form.cleaned_data['amount']
        approved_count = Transaction.objects.filter(
            account=self.request.user.account,
            transaction_type=LOAN,
            loan_approve=True
        ).count()
        if approved_count >= 3:
            return HttpResponse('Loan limit exceeded')

        messages.success(self.request, f'Loan request for {amount:,.2f}$ submitted')
        send_transaction_email(self.request.user, amount, 'Loan Request Message', 'transactions/loan_email.html')
        return super().form_valid(form)

class TransactionReportView(LoginRequiredMixin, ListView):
    """Displays the user's transactions and balance, with optional date filtering."""
    template_name = 'transactions/transaction_report.html'
    model = Transaction
    balance = 0

    def get_queryset(self):
        qs = super().get_queryset().filter(account=self.request.user.account)
        start = self.request.GET.get('start_date')
        end = self.request.GET.get('end_date')
        if start and end:
            start_date = datetime.strptime(start, '%Y-%m-%d').date()
            end_date = datetime.strptime(end, '%Y-%m-%d').date()
            qs = qs.filter(timestamp__date__gte=start_date, timestamp__date__lte=end_date)
            self.balance = Transaction.objects.filter(
                timestamp__date__gte=start_date,
                timestamp__date__lte=end_date
            ).aggregate(Sum('amount'))['amount__sum']
        else:
            self.balance = self.request.user.account.balance
        return qs.distinct()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['account'] = self.request.user.account
        return context

class PayLoanView(LoginRequiredMixin, View):
    """Processes repayment of an approved loan if the user has enough balance."""
    def get(self, request, loan_id):
        loan = get_object_or_404(Transaction, id=loan_id)
        if loan.loan_approve:
            account = loan.account
            if account.balance >= loan.amount:
                account.balance -= loan.amount
                loan.balance_after_transaction = account.balance
                account.save(update_fields=['balance'])
                loan.transaction_type = LOAN_PAID
                loan.save(update_fields=['transaction_type', 'balance_after_transaction'])
                return redirect('loan_list')
            messages.error(request, 'Insufficient balance to pay loan')
        return redirect('loan_list')

class LoanListView(LoginRequiredMixin, ListView):
    """Lists all loan transactions (requests) for the user."""
    model = Transaction
    template_name = 'transactions/loan_request.html'
    context_object_name = 'loans'

    def get_queryset(self):
        return Transaction.objects.filter(
            account=self.request.user.account,
            transaction_type=LOAN
        )

class TransferView(FormView):
    """Transfers funds to another account by account number, updating both balances."""
    template_name = 'transactions/transfer.html'
    form_class = TransactionForm
    success_url = reverse_lazy('loan_list')

    def form_valid(self, form):
        account_no = form.cleaned_data['account_number']
        amount = form.cleaned_data['amount']
        recipient = UserBankAccount.objects.filter(account_no=account_no).first()
        if amount > self.request.user.account.balance:
            messages.error(self.request, 'Transfer amount exceeds balance')
            return redirect('transfer')

        recipient.balance += amount
        recipient.save(update_fields=['balance'])
        sender = self.request.user.account
        sender.balance -= amount
        sender.save(update_fields=['balance'])

        messages.success(self.request, 'Transfer completed')
        return super().form_valid(form)
