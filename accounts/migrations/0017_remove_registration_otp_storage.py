from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0016_preserve_legacy_verified_users'),
    ]

    operations = [
        migrations.RemoveField(model_name='user', name='otp'),
        migrations.RemoveField(model_name='user', name='otp_created_at'),
        migrations.RemoveField(model_name='user', name='otp_attempts'),
    ]
