from django.contrib import admin
from .models import Category, SubCategory, Brand, Unit, Banner, AdvBanner

admin.site.register(Category)
admin.site.register(SubCategory)
admin.site.register(Brand)
admin.site.register(Unit)
admin.site.register(Banner)
admin.site.register(AdvBanner)