import json
from django.http import FileResponse
import requests
from django.shortcuts import render, redirect
from .forms import UploadFileForm, LoginForm
from io import BytesIO
import mimetypes


def home(request):
    return render(request, 'index.html')

def test(request):
    return render(request, 'test.html')

def logout_view(request):
    request.session.flush()
    return redirect('home')

def register_view(request):
    base_url = "http://127.0.0.1:8000"
    
    if request.method == 'POST':
        form = LoginForm(request.POST)
        
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            coldkey = form.cleaned_data.get('coldkey')
            hotkey = form.cleaned_data.get('hotkey')
            
            if username and password:
                response = requests.post(f'{base_url}/register/', json={'username': username, 'password': password, 'hotkey': hotkey, 'coldkey': coldkey})
                    
                if response.status_code == 200:
                    data = response.json()
                    request.session['username'] = username  # Set the session variable
                    
                    # get token
                    token_response = requests.post(f'{base_url}/token', data={"username": username, "password": password})
                    
                    request.session['token'] = token_response.json()['access_token']
                    
                    return render(request, 'index.html')

                elif response.status_code == 400:
                    # get token
                    token_response = requests.post(f'{base_url}/token', data={"username": username, "password": password})
                
                    if token_response.status_code == 200:
                        data = token_response.json()
                        request.session['username'] = username
                        request.session['token'] = data['access_token']
                        
                        return render(request, 'index.html')
                    else:
                        data = token_response.json()
                        request.session['username'] = None
                        request.session['token'] = None
                        
                        return render(request, 'accounts/register.html', {'data': data})
                else:
                    data = response.json()
                    return render(request, 'accounts/register.html', {'data': data})   
                
    else:
        form = LoginForm()
        
    return render(request, 'accounts/register.html', {'form': form})

def login_view(request):
    base_url = "http://127.0.0.1:8000"
    if request.method == 'POST':
        form = LoginForm(request.POST)
        
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            if username and password:
                data = {"username": username, "password": password}
                
                response = requests.post(f'{base_url}/token', data=data)
                if response.status_code == 200:
                    data = response.json()
                    request.session['username'] = username  # Set the session variable
                    request.session['token'] = data['access_token']
                    
                    return render(request, 'index.html')
                else:
                    data = response.json()
                    return render(request, 'accounts/login.html', {'data': data}) 
    else:
        form = LoginForm()
                    
    return render(request, 'accounts/login.html', {'form': form})

def upload_file_view(request):
    base_url = "http://127.0.0.1:8000"
    print(request.FILES)
    
    if request.method == 'POST':
        form = UploadFileForm(request.POST, request.FILES)
        if form.is_valid():
            files = request.FILES.getlist('file')
            token = request.session.get('token')
            
            files = [('files', (file.name, file, mimetypes.guess_type(file.name)[0] or 'application/octet-stream')) for file in files]
            headers = {'Authorization': f'Bearer {token}'}

            response = requests.post(f'{base_url}/uploadfiles/', files=files, headers=headers)

            try:
                return render(request, 'accounts/upload.html', {'data': response.json()})
            except json.decoder.JSONDecodeError:
                return render(request, 'accounts/upload.html', {'error': 'The server returned an empty response'})
    else:
        form = UploadFileForm()
    return render(request, 'accounts/upload.html', {'form': form})
    
def retrieve_file_view(request):
    base_url = "http://127.0.0.1:8000"
    if request.method == 'POST':
        token = request.session.get('token')
        file_hash = request.POST.get('filehash')
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(f"{base_url}/retrieve/{file_hash}", headers=headers)
        if response.headers.get('Content-Type') == 'application/json':
            # Handle JSON response
            return render(request, 'accounts/retrieve.html', {'data': response})
        else:
             # Create a file-like object from the content
            file = BytesIO(response.content)

            # Create a FileResponse and set the Content-Disposition header to prompt the browser to download the file
            response = FileResponse(file)
            response['Content-Disposition'] = f'attachment; filename={file_hash}'
            return response  # Return the FileResponse object directly

    return render(request, 'accounts/retrieve.html')
        