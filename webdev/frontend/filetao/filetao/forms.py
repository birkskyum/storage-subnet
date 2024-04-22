# forms.py

from django import forms

class UploadFileForm(forms.Form):
    file = forms.FileField()
    
class LoginForm(forms.Form):
    username = forms.CharField(widget=forms.TextInput(attrs={"type": "username", "name": "username", "placeholder": "Username"}), max_length=100, required=True)
    password = forms.CharField(widget=forms.TextInput(attrs={"type": "password", "name": "password", "placeholder": "Password"}), required=True)
    coldkey = forms.CharField(widget=forms.TextInput(attrs={"type": "username", "name": "coldkey", "placeholder": "Coldkey Mnemonic"}), max_length=100, required=False)
    hotkey = forms.CharField(widget=forms.TextInput(attrs={"type": "username", "name": "hotkey", "placeholder": "Hotkey Mnemonic"}), max_length=100, required=False)