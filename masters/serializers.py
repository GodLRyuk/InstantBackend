from rest_framework import serializers
from .models import Category, SubCategory, Brand, Unit, Banner, AdvBanner

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = '__all__'


class SubCategorySerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)

    class Meta:
        model = SubCategory
        fields = ['id', 'name', 'category', 'category_name']

class BrandSerializer(serializers.ModelSerializer):
    class Meta:
        model = Brand
        fields = '__all__'


class UnitSerializer(serializers.ModelSerializer):
    name= serializers.CharField(required=True)
    short_name = serializers.CharField(required=True)

    class Meta:
        model = Unit
        fields = '__all__'
class BannerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Banner
        fields = '__all__' 
class ADvBannerSerializer(serializers.ModelSerializer):
    class Meta:
        model = AdvBanner
        fields = '__all__' 