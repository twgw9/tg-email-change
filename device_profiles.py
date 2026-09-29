import random

DEVICE_MODELS = [
    {"device_model": "Samsung Galaxy S23 Ultra", "system_version": "Android 14", "app_version": "10.9.1", "lang_code": "en", "system_lang_code": "en-US"},
    {"device_model": "Google Pixel 8 Pro", "system_version": "Android 14", "app_version": "10.9.2", "lang_code": "en", "system_lang_code": "en-US"},
    {"device_model": "Xiaomi 13 Pro", "system_version": "Android 13", "app_version": "10.8.3", "lang_code": "en", "system_lang_code": "en-US"},
    {"device_model": "OnePlus 11", "system_version": "Android 14", "app_version": "10.9.0", "lang_code": "en", "system_lang_code": "en-IN"},
    {"device_model": "iPhone 15 Pro Max", "system_version": "iOS 17.4.1", "app_version": "10.8.1", "lang_code": "en", "system_lang_code": "en-US"},
    {"device_model": "iPhone 14 Pro", "system_version": "iOS 16.6", "app_version": "10.7.0", "lang_code": "en", "system_lang_code": "en-GB"},
    {"device_model": "Samsung Galaxy A54 5G", "system_version": "Android 13", "app_version": "10.8.2", "lang_code": "en", "system_lang_code": "en-US"},
    {"device_model": "Realme GT Neo 5", "system_version": "Android 13", "app_version": "10.8.0", "lang_code": "en", "system_lang_code": "en-IN"},
    {"device_model": "Motorola Edge 40 Pro", "system_version": "Android 13", "app_version": "10.7.2", "lang_code": "en", "system_lang_code": "en-US"},
    {"device_model": "Vivo X90 Pro", "system_version": "Android 13", "app_version": "10.8.1", "lang_code": "en", "system_lang_code": "en-IN"},
    {"device_model": "Oppo Find X6 Pro", "system_version": "Android 14", "app_version": "10.9.0", "lang_code": "en", "system_lang_code": "en-US"},
    {"device_model": "POCO F5 Pro", "system_version": "Android 13", "app_version": "10.7.4", "lang_code": "en", "system_lang_code": "en-IN"},
    {"device_model": "Sony Xperia 1 V", "system_version": "Android 13", "app_version": "10.8.0", "lang_code": "en", "system_lang_code": "en-GB"},
    {"device_model": "Asus ROG Phone 7", "system_version": "Android 13", "app_version": "10.7.3", "lang_code": "en", "system_lang_code": "en-US"},
    {"device_model": "Honor Magic 5 Pro", "system_version": "Android 13", "app_version": "10.8.2", "lang_code": "en", "system_lang_code": "en-US"},
    {"device_model": "Samsung Galaxy S22+", "system_version": "Android 13", "app_version": "10.6.5", "lang_code": "en", "system_lang_code": "en-US"},
    {"device_model": "Google Pixel 7a", "system_version": "Android 14", "app_version": "10.9.1", "lang_code": "en", "system_lang_code": "en-US"},
    {"device_model": "iPhone 13", "system_version": "iOS 16.5", "app_version": "10.5.2", "lang_code": "en", "system_lang_code": "en-US"},
    {"device_model": "Nothing Phone (2)", "system_version": "Android 13", "app_version": "10.8.0", "lang_code": "en", "system_lang_code": "en-GB"},
    {"device_model": "OnePlus Nord 3", "system_version": "Android 13", "app_version": "10.7.1", "lang_code": "en", "system_lang_code": "en-IN"},
    {"device_model": "Samsung Galaxy Z Fold 5", "system_version": "Android 13", "app_version": "10.8.3", "lang_code": "en", "system_lang_code": "en-US"},
    {"device_model": "Xiaomi Redmi Note 13 Pro+", "system_version": "Android 13", "app_version": "10.8.1", "lang_code": "en", "system_lang_code": "en-IN"},
    {"device_model": "Motorola Razr 40 Ultra", "system_version": "Android 13", "app_version": "10.7.5", "lang_code": "en", "system_lang_code": "en-US"},
    {"device_model": "iQOO 11 5G", "system_version": "Android 13", "app_version": "10.7.2", "lang_code": "en", "system_lang_code": "en-IN"},
    {"device_model": "Huawei P60 Pro", "system_version": "EMUI 13.1", "app_version": "10.6.0", "lang_code": "en", "system_lang_code": "en-US"},
    {"device_model": "Samsung Galaxy Tab S9", "system_version": "Android 13", "app_version": "10.8.0", "lang_code": "en", "system_lang_code": "en-US"},
    {"device_model": "iPad Pro 12.9", "system_version": "iPadOS 17.2", "app_version": "10.8.2", "lang_code": "en", "system_lang_code": "en-US"},
    {"device_model": "ZTE Nubia RedMagic 8S Pro", "system_version": "Android 13", "app_version": "10.7.0", "lang_code": "en", "system_lang_code": "en-US"},
    {"device_model": "Google Pixel Fold", "system_version": "Android 14", "app_version": "10.9.0", "lang_code": "en", "system_lang_code": "en-US"},
    {"device_model": "OnePlus Open", "system_version": "Android 13", "app_version": "10.8.4", "lang_code": "en", "system_lang_code": "en-IN"}
]

def get_random_device():
    return random.choice(DEVICE_MODELS)
