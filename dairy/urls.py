from django.urls import path

from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('delivery/', views.delivery_dashboard, name='delivery_dashboard'),
    path('delivery/notifications/', views.delivery_notifications, name='delivery_notifications'),
    path('delivery/history/', views.delivery_date_history, name='delivery_date_history'),

    path('customers/', views.customer_list, name='customer_list'),
    path('customers/add/', views.customer_create, name='customer_create'),
    path('customers/<int:pk>/edit/', views.customer_update, name='customer_update'),
    path('customers/<int:pk>/delete/', views.customer_delete, name='customer_delete'),
    path('customers/<int:pk>/', views.customer_detail, name='customer_detail'),

    path('delivery/<str:mode>/start/', views.delivery_mode_start, name='delivery_mode_start'),
    path('delivery/<str:mode>/', views.delivery_mode, name='delivery_mode'),
    path('delivery/<str:mode>/summary/', views.delivery_summary, name='delivery_summary'),

    path('customers/<int:customer_id>/review/', views.monthly_review, name='monthly_review'),

    path('feed-sacks/', views.feed_sack_list, name='feed_sack_list'),
    path('feed-sacks/add/', views.feed_sack_create, name='feed_sack_create'),

    path('cows/', views.cow_list, name='cow_list'),
    path('cows/add/', views.cow_create, name='cow_create'),
    path('cows/<int:pk>/', views.cow_detail, name='cow_detail'),
    path('cows/<int:pk>/edit/', views.cow_update, name='cow_update'),
    path('cows/<int:pk>/health/', views.cow_health, name='cow_health'),
    path('cows/<int:pk>/medicine/', views.cow_medicine_edit, name='cow_medicine_edit'),
    path('cows/<int:pk>/medicine/<str:medicine_type>/history/', views.cow_medicine_history, name='cow_medicine_history'),
    path('cows/<int:pk>/sell/', views.cow_sell, name='cow_sell'),
    path('marketplace/', views.marketplace_list, name='marketplace_list'),
    path('marketplace/cow/<int:pk>/', views.cow_shop_record, name='cow_shop_record'),
    path('marketplace/cow/<int:pk>/detail/', views.marketplace_cow_detail, name='marketplace_cow_detail'),
    path('diseases/add/', views.disease_create, name='disease_create'),
    path('settings/', views.settings, name='settings'),
    path('settings/reset/', views.reset_data, name='reset_data'),
]
