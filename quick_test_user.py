import requests

resp = requests.post('http://localhost:8000/auth/register', json={
    'email': 'test@lyo.app',
    'username': 'testuser',
    'password': 'testpassword123',
    'confirm_password': 'testpassword123',
    'first_name': 'Test',
    'last_name': 'User'
})

if resp.status_code == 200:
    print('✅ User created successfully')
else:
    print(f'Status: {resp.status_code}')
    print('Trying login...')
    login = requests.post('http://localhost:8000/auth/login', json={
        'email': 'test@lyo.app',
        'password': 'testpassword123'
    })
    if login.status_code == 200:
        print('✅ Login successful - user exists')
    else:
        print(f'❌ Failed: {login.status_code}')
