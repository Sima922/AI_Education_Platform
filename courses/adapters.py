from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.socialaccount.models import SocialAccount
from django.contrib.auth import get_user_model
import logging

logger = logging.getLogger(__name__)

User = get_user_model()

class CustomAccountAdapter(DefaultAccountAdapter):
    """Custom account adapter for regular account operations"""
    pass

class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    """Custom social account adapter to handle orphaned social accounts"""
    
    def pre_social_login(self, request, sociallogin):
        """
        Handle the case where a SocialAccount exists but the associated User doesn't
        """
        try:
            # Check if this social account already exists
            if sociallogin.account.uid and sociallogin.account.provider:
                existing_social_account = SocialAccount.objects.filter(
                    uid=sociallogin.account.uid,
                    provider=sociallogin.account.provider
                ).first()
                
                if existing_social_account:
                    try:
                        # Try to access the user - this will raise DoesNotExist if user is missing
                        user = existing_social_account.user
                        logger.info(f"Found existing social account with valid user: {user.email}")
                    except User.DoesNotExist:
                        # User doesn't exist but social account does - clean up the orphaned record
                        logger.warning(f"Found orphaned social account {existing_social_account.uid}, cleaning up")
                        try:
                            existing_social_account.delete()
                            logger.info("Successfully cleaned up orphaned social account")
                        except Exception as e:
                            logger.error(f"Error cleaning up orphaned social account: {e}")
                            
        except Exception as e:
            logger.error(f"Error in pre_social_login: {e}")
        
        super().pre_social_login(request, sociallogin)

    def save_user(self, request, sociallogin, form=None):
        """
        Save the user and handle any additional setup
        """
        try:
            user = super().save_user(request, sociallogin, form)
            logger.info(f"Successfully created/updated user: {user.email}")
            return user
        except Exception as e:
            logger.error(f"Error saving user: {e}")
            raise