from OpenSSL.rand import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from accounts.models import DriverAttendance


class DriverStatusAPIView(APIView):
    permission_classes = [IsAuthenticated]

    # ================= HELPER =================
    def _auto_clockout_previous(self, user):
        today = timezone.now().date()
        previous_open = DriverAttendance.objects.filter(
            driver=user,
            clock_out_time=None,
        ).exclude(date=today)

        for record in previous_open:
            end_of_day = timezone.datetime.combine(
                record.date,
                timezone.datetime.max.time(),
                tzinfo=timezone.get_current_timezone()
            )
            record.clock_out_time = end_of_day
            record.calculate_total_hours()
            if record.total_hours and record.total_hours < 4:
                record.status = 'half_day'
            record.save()

    # ================= GET =================
    def get(self, request):
        user = request.user

        if user.role not in ("DELIVERY", "PICKUP"):
            return Response(
                {'error': 'Not a driver or picker account'},
                status=status.HTTP_403_FORBIDDEN
            )

        today = timezone.now().date()

        # ✅ auto clock-out previous day
        self._auto_clockout_previous(user)

        # ✅ get latest open record today
        attendance = DriverAttendance.objects.filter(
            driver=user,
            date=today,
            clock_out_time=None
        ).last()

        # if no open record get last completed one
        if not attendance:
            attendance = DriverAttendance.objects.filter(
                driver=user,
                date=today
            ).last()

        return Response({
            "is_online": user.is_online,
            "attendance": {
                "clock_in_time": attendance.clock_in_time if attendance else None,
                "clock_out_time": attendance.clock_out_time if attendance else None,
                "total_hours": attendance.total_hours if attendance else None,
                "status": attendance.status if attendance else "absent",
            }
        })

    # ================= POST =================
    def post(self, request):
        user = request.user

        if user.role not in ("DELIVERY", "PICKUP"):
            return Response(
                {'error': 'Not a driver or picker account'},
                status=status.HTTP_403_FORBIDDEN
            )

        is_online = request.data.get("is_online")

        if is_online is None:
            return Response({"error": "is_online required"}, status=400)

        today = timezone.now().date()
        now = timezone.now()

        # ✅ auto clock-out previous day
        self._auto_clockout_previous(user)

        # ✅ GOING ONLINE → always create a NEW record
        if is_online:
            DriverAttendance.objects.create(
                driver=user,
                date=today,
                clock_in_time=now,
                status='present'
            )

        # ✅ GOING OFFLINE → update the latest open record only
        else:
            attendance = DriverAttendance.objects.filter(
                driver=user,
                date=today,
                clock_out_time=None
            ).last()

            if attendance:
                attendance.clock_out_time = now
                attendance.calculate_total_hours()
                if attendance.total_hours and attendance.total_hours < 4:
                    attendance.status = 'half_day'
                attendance.save()

        user.is_online = is_online
        user.save()

        return Response({
            "is_online": user.is_online
        })


class DriverAttendanceAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        if user.role not in ("DELIVERY", "PICKUP"):
            return Response(
                {'error': 'Not a driver or picker account'},
                status=status.HTTP_403_FORBIDDEN
            )

        # ✅ last 30 records
        history = DriverAttendance.objects.filter(
            driver=user
        ).order_by('-clock_in_time')[:30]

        # this month summary
        current_month = timezone.now().month
        current_year = timezone.now().year
        monthly = DriverAttendance.objects.filter(
            driver=user,
            date__month=current_month,
            date__year=current_year
        )

        # ✅ count unique present days
        present_days = monthly.filter(
            status='present'
        ).values('date').distinct().count()

        half_days = monthly.filter(
            status='half_day'
        ).values('date').distinct().count()

        total_hours = sum(
            float(a.total_hours) for a in monthly if a.total_hours
        )

        return Response({
            "monthly_summary": {
                "present_days": present_days,
                "half_days": half_days,
                "total_hours": round(total_hours, 2),
            },
            "history": [
                {
                    "date": a.date,
                    "clock_in_time": a.clock_in_time,
                    "clock_out_time": a.clock_out_time,
                    "total_hours": a.total_hours,
                    "status": a.status,
                }
                for a in history
            ]
        })