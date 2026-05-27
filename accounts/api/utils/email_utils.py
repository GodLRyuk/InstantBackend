from django.core.mail import send_mail
from django.conf import settings

def send_otp_email(email, otp):
    subject = "Your OTP Verification Code"
    message = f"""
    Hello,

    Your OTP code is: {otp}

    It is valid for 5 minutes.

    Thank you.
    """

    send_mail(
        subject,
        message,
        settings.EMAIL_HOST_USER,
        [email],
        fail_silently=False
    )