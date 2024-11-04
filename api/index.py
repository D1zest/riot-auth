from flask import Flask, render_template, request, jsonify
import requests
from urllib.parse import unquote
import uuid
import time

app = Flask(__name__)

TOKEN_RETRY_INTERVAL = 2
QR_REGENERATION_INTERVAL = 60

def translate_text(text, language):
    if language == "ko":
        return text
    from easygoogletranslate import EasyGoogleTranslate

    translator = EasyGoogleTranslate(
        source_language = 'ko',
        target_language = language,
        timeout=10
    )

    result = translator.translate(text)
    return result

def new_session():
    session = requests.Session()
    return session, str(uuid.uuid4())

def login_url():
    session, sdk_sid = new_session()
    
    trace_id = uuid.uuid4().hex
    parent_id = uuid.uuid4().hex[:16]
    traceparent = f'00-{trace_id}-{parent_id}-00'

    headers1 = {
        'Host': 'clientconfig.rpg.riotgames.com',
        'user-agent': 'RiotGamesApi/24.9.1.4445 client-config (Windows;10;;Professional, x64) riot_client/0',
        'Accept-Encoding': 'deflate, gzip, zstd',
        'Accept': 'application/json',
        'Connection': 'keep-alive',
        'baggage': f'sdksid={sdk_sid}',
        'traceparent': traceparent
    }

    url1 = 'https://clientconfig.rpg.riotgames.com/api/v1/config/public'
    params = {
        'os': 'windows',
        'region': 'KR',
        'app': 'Riot Client',
        'version': '97.0.1.2366',
        'patchline': 'KeystoneFoundationLiveWin'
    }

    response1 = session.get(url1, headers=headers1, params=params)

    headers2 = {
        'Host': 'auth.riotgames.com',
        'user-agent': 'RiotGamesApi/24.9.1.4445 rso-auth (Windows;10;;Professional, x64) riot_client/0',
        'Accept-Encoding': 'deflate, gzip, zstd',
        'Accept': 'application/json',
        'Connection': 'keep-alive',
        'baggage': f'sdksid={sdk_sid}',
        'traceparent': traceparent,
    }

    session.get('https://auth.riotgames.com/.well-known/openid-configuration', headers=headers2)

    login_data = {
        "apple": None,
        "campaign": None,
        "clientId": "riot-client",
        "code": None,
        "facebook": None,
        "gamecenter": None,
        "google": None,
        "language": "ko_KR",
        "mockDeviceId": None,
        "mockPlatform": None,
        "multifactor": None,
        "nintendo": None,
        "platform": "windows",
        "playstation": None,
        "qrcode": {},
        "remember": False,
        "riot_identity": None,
        "riot_identity_signup": None,
        "rso": None,
        "sdkVersion": "24.9.1.4445",
        "type": "auth",
        "xbox": None
    }

    headers3 = {
        'Host': 'authenticate.riotgames.com',
        'user-agent': 'RiotGamesApi/24.9.1.4445 rso-authenticator (Windows;10;;Professional, x64) riot_client/0',
        'Accept-Encoding': 'deflate, gzip, zstd',
        'Accept': 'application/json',
        'Connection': 'keep-alive',
        'Content-Type': 'application/json',
        'baggage': f'sdksid={sdk_sid}',
        'traceparent': traceparent,
    }

    response3 = session.post('https://authenticate.riotgames.com/api/v1/login', headers=headers3, json=login_data)
    response_json = response3.json()

    cluster = response_json.get("cluster")
    suuid = response_json.get("suuid")
    timestamp = response_json.get("timestamp")

    if not cluster or not suuid or not timestamp:
        return None, "필수 데이터가 응답에 없습니다."
    
    login_url = f'https://qrlogin.riotgames.com/riotmobile/?cluster={cluster}&suuid={suuid}&timestamp={timestamp}&utm_source=riotclient&utm_medium=client&utm_campaign=qrlogin-riotmobile'
    
    return {
        'login_url': login_url,
        'session': session,
        'sdk_sid': sdk_sid
    }, None

def get_token(session, sdk_sid):
    traceparent = f'00-{uuid.uuid4().hex}-{uuid.uuid4().hex[:16]}-00'
    check_headers = {
        'Host': 'authenticate.riotgames.com',
        'user-agent': 'RiotGamesApi/24.9.1.4445 rso-authenticator (Windows;10;;Professional, x64) riot_client/0',
        'Accept-Encoding': 'deflate, gzip, zstd',
        'Accept': 'application/json',
        'Connection': 'keep-alive',
        'Content-Type': 'application/json',
        'baggage': f'sdksid={sdk_sid}',
        'traceparent': traceparent
    }

    start_time = time.time()
    while time.time() - start_time < QR_REGENERATION_INTERVAL:
        response = session.get('https://authenticate.riotgames.com/api/v1/login', headers=check_headers)
        if response.status_code == 200:
            return response.json(), None
        time.sleep(TOKEN_RETRY_INTERVAL)
    return None, "1분 경과: QR 코드를 다시 생성합니다."

current_session_data = None

@app.route('/login_url', methods=['POST'])
def login_url_route():
    global current_session_data
    result, error = login_url()
    if error:
        return jsonify({'error': error}), 400
    
    current_session_data = {
        'session': result['session'],
        'sdk_sid': result['sdk_sid']
    }
    
    return jsonify({
        'login_url': result['login_url']
    })

@app.route('/get_token', methods=['POST'])
def fetch_token():
    global current_session_data
    
    if not current_session_data:
        return jsonify({'error': 'No active session'}), 400
    
    token_data, error = get_token(
        current_session_data['session'], 
        current_session_data['sdk_sid']
    )
    
    if error:
        new_url, url_error = login_url()
        if url_error:
            return jsonify({'error': url_error}), 400
        
        current_session_data = {
            'session': new_url['session'],
            'sdk_sid': new_url['sdk_sid']
        }
        
        return jsonify({
            'error': error, 
            'new_url': new_url['login_url']
        })
    
    return jsonify(token_data)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/auth/<lang>/')
def auth(lang):
    language = unquote(lang)
    
    title = translate_text('로그인', language)
    dis = translate_text('라이엇 모바일을 통해 로그인', language)
    wait = translate_text('로그인 Url 생성중..', language)
    fail = translate_text('로그인 Url 생성 실패', language)
    md = translate_text('모바일 환경에서 바로 로그인하기', language)
    plzscan = translate_text('QR코드를 스캔하거나 Url에 방문해주세요.', language)
    end = translate_text('로그인 Url만료 새 Url을 생성합니다.', language)
    rm = translate_text('남은 시간', language)
    tf = translate_text('토큰 확인 중 오류 발생', language)
    sus = translate_text('로그인 완료', language)

    return render_template('auth.html',
                           title = title,
                           dis = dis,
                           wait = wait,
                           fail = fail,
                           md = md,
                           plzscan = plzscan,
                           end = end,
                           rm = rm,
                           tf = tf,
                           sus = sus)

if __name__ == '__main__':
    app.run(debug=True)
