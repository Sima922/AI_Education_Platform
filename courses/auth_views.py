from django.shortcuts import render, redirect
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from allauth.socialaccount.models import SocialAccount
from django.urls import reverse_lazy
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login
from django.views.generic import CreateView
from .models import User
import logging
from django.contrib.auth import login, get_backends

logger = logging.getLogger(__name__)


class CustomUserCreationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ('email', 'first_name', 'last_name', 'password1', 'password2')
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'].required = True
        self.fields['first_name'].required = True
        self.fields['last_name'].required = True

class SignUpView(CreateView):
    form_class = CustomUserCreationForm
    template_name = 'registration/signup.html'
    success_url = reverse_lazy('courses:homepage')
    
    def form_valid(self, form):
        response = super().form_valid(form)
        backend = get_backends()[0]  # Default to the first backend
        login(self.request, self.object, backend=backend.__module__ + '.' + backend.__class__.__name__)
        messages.success(self.request, 'Account created successfully! Welcome!')
        return response

def custom_logout_view(request):
    """Custom logout view"""
    logout(request)
    messages.success(request, 'You have been successfully logged out.')
    return redirect('courses:homepage')

@login_required
def profile_view(request):
    """User profile view with better error handling"""
    google_data = None
    
    try:
        # Use the safer method to get social account
        social_account = request.user.get_social_account('google')
        if social_account:
            google_data = social_account.extra_data
    except Exception as e:
        logger.error(f"Error getting social account data: {e}")
        # Optionally clean up any orphaned accounts for this user
        from allauth.socialaccount.models import SocialAccount
        orphaned = SocialAccount.objects.filter(user=request.user, provider='google')
        for account in orphaned:
            try:
                # Test if the account is actually valid
                test_user = account.user
            except User.DoesNotExist:
                account.delete()
                logger.info(f"Cleaned up orphaned social account for user {request.user.id}")
    
    context = {
        'user': request.user,
        'google_data': google_data,
    }
    return render(request, 'registration/profile.html', context)

def auth_status(request):
    """API endpoint to check authentication status"""
    if request.user.is_authenticated:
        return JsonResponse({
            'authenticated': True,
            'username': request.user.username,
            'email': request.user.email,
            'first_name': request.user.first_name,
            'last_name': request.user.last_name,
            'is_creator': getattr(request.user, 'is_creator', False)
        })
    else:
        return JsonResponse({'authenticated': False})