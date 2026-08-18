import time
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from apps.users.models import UserConfig
from core.services.sms_hub import get_sms_provider

class Command(BaseCommand):
    help = 'Test buying a number from the configured SMS provider based on UserConfig'

    def add_arguments(self, parser):
        parser.add_argument('username', type=str, help='The username whose config to test')

    def handle(self, *args, **options):
        username = options['username']
        try:
            user = User.objects.get(username=username)
            config = user.userconfig
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"User {username} not found."))
            return
        except UserConfig.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"UserConfig for {username} not found."))
            return

        if not config.sms_provider or not config.default_country:
            self.stdout.write(self.style.ERROR("UserConfig must have sms_provider and default_country set."))
            return

        provider = get_sms_provider(config)
        
        self.stdout.write(f"Testing SMS Provider: {config.sms_provider.name}")
        self.stdout.write(f"Default Country: {config.default_country.name}")
        self.stdout.write(f"Max Price: {config.max_price}")
        
        try:
            balance = provider.get_balance()
            self.stdout.write(self.style.SUCCESS(f"Current Balance: {balance}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to get balance: {e}"))
            return

        # Get mapping
        mapping = config.default_country.provider_mappings.filter(provider=config.sms_provider).first()
        if not mapping:
            self.stdout.write(self.style.ERROR("No provider mapping found for this country and provider. Did you run sync_countries?"))
            return

        self.stdout.write(f"Requesting FACEBOOK number in country ID {mapping.provider_country_id}...")
        
        try:
            number_data = provider.get_number(
                mapping.provider_country_id, 
                service="FACEBOOK", 
                max_price=config.max_price
            )
            
            phone = number_data['phone']
            activation_id = number_data['activation_id']
            
            self.stdout.write(self.style.SUCCESS(f"Successfully bought number: {phone} (ID: {activation_id})"))
            
            self.stdout.write("Waiting 5 seconds before cancelling...")
            time.sleep(5)
            
            cancel_status = provider.cancel_number(activation_id)
            self.stdout.write(self.style.SUCCESS(f"Cancellation status: {cancel_status}"))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to get number: {e}"))
