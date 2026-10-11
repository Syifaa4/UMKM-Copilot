from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers


class DaftarSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(
        max_length=128, write_only=True, trim_whitespace=False
    )
    nama_umkm = serializers.CharField(max_length=100)
    email = serializers.EmailField(required=False, allow_blank=True, default="")

    def validate_username(self, value):
        for validator in User._meta.get_field("username").validators:
            validator(value)  # error Django ditangkap DRF
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("Username sudah dipakai.")
        return value

    def validate(self, attrs):
        sementara = User(username=attrs["username"], email=attrs.get("email", ""))
        try:
            validate_password(attrs["password"], user=sementara)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)})
        return attrs