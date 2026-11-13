"""Desktop bridge to the private merchant API. Credentials never enter UI state."""
from __future__ import annotations
import json
import threading
import time
from urllib import request, error
from urllib.parse import urlsplit

class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

class MerchantClient:
    def __init__(self, url='', allow_local_demo=False):
        self.url = url.rstrip('/')
        parsed = urlsplit(self.url)
        local = parsed.scheme == 'http' and parsed.hostname == '127.0.0.1' and allow_local_demo
        self.configured = bool(self.url and (parsed.scheme == 'https' or local) and parsed.netloc
                               and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment)
        self._token = ''
        self._expires = 0
        self._lock = threading.RLock()
        self._state = {'configured':self.configured, 'authenticated':False, 'demo':True,
                       'sales_enabled':False, 'active':False, 'orders':[], 'referral':{},
                       'error':'' if self.configured else 'server_not_configured'}
        self._opener = request.build_opener(NoRedirect())

    def snapshot(self):
        with self._lock:
            result = dict(self._state)
            if time.time() >= self._expires:
                result.update(authenticated=False, active=False)
            return result

    def _call(self, path, data=None, auth=True):
        if not self.configured:
            return {'ok':False, 'error':'server_not_configured'}
        if auth and (not self._token or time.time() >= self._expires):
            return {'ok':False, 'error':'authentication_required'}
        headers = {'Content-Type':'application/json'}
        if auth:
            headers['Authorization'] = 'Bearer ' + self._token
        req = request.Request(self.url + '/api/v1/' + path,
                              data=json.dumps(data).encode() if data is not None else None, headers=headers)
        try:
            with self._opener.open(req, timeout=6) as response:
                raw = response.read(262145)
            if len(raw) > 262144:
                raise ValueError('oversized response')
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise ValueError('invalid response')
            return {'ok':True, **result}
        except error.HTTPError as exc:
            if exc.code in (401,403) and auth:
                self._token = ''
                self._state.update(authenticated=False, active=False)
            return {'ok':False, 'error':{401:'authentication_required',403:'authentication_required',409:'order_conflict',429:'rate_limited'}.get(exc.code,'server_rejected')}
        except (OSError, ValueError, error.URLError):
            return {'ok':False, 'error':'server_unavailable'}

    def login(self, credential):
        if not isinstance(credential,str) or not 1 <= len(credential.strip()) <= 512:
            return {'ok':False,'error':'invalid_credential'}
        with self._lock:
            self._token = ''
            self._state.update(authenticated=False,active=False,orders=[],referral={})
            result = self._call('session', {'credential':credential.strip()}, auth=False)
            token = result.get('token')
            if not result.get('ok') or not isinstance(token,str) or not token:
                return {'ok':False,'error':result.get('error','invalid_session')}
            self._token = token
            self._expires = time.time() + min(3600,max(0,int(result.get('expires_in',0))))
            return self.refresh()

    def refresh(self):
        with self._lock:
            catalog = self._call('catalog',auth=False)
            if catalog.get('ok'):
                self._state.update(demo=catalog.get('demo') is True,
                                   sales_enabled=catalog.get('sales_enabled') is True,
                                   plans=catalog.get('plans',[]))
            entitlement = self._call('entitlement')
            if not entitlement.get('ok'):
                self._state.update(active=False,error=entitlement.get('error'))
                return {'ok':False,**self.snapshot()}
            self._state.update(authenticated=True,active=entitlement.get('active') is True,
                               expires_at=entitlement.get('expires_at'),error='')
            for endpoint in ('orders','referral'):
                result = self._call(endpoint)
                if result.get('ok'):
                    self._state[endpoint] = result.get('orders',[]) if endpoint == 'orders' else {k:v for k,v in result.items() if k!='ok'}
            return {'ok':True,**self.snapshot()}

    def create_order(self, plan, method, request_id):
        if plan not in ('day','three_days','week') or method not in ('bank_transfer','steam_items'):
            return {'ok':False,'error':'invalid_order'}
        if not isinstance(request_id,str) or not 8 <= len(request_id) <= 80 or not all(c.isascii() and (c.isalnum() or c in '_-') for c in request_id):
            return {'ok':False,'error':'invalid_request_id'}
        with self._lock:
            result = self._call('orders',dict(plan=plan,method=method,request_id=request_id))
            if result.get('ok'): self.refresh()
            return result

    def submit(self, order_id):
        if not isinstance(order_id,str) or not 1 <= len(order_id) <= 100 or not all(c.isascii() and (c.isalnum() or c in '_-') for c in order_id):
            return {'ok':False,'error':'invalid_order'}
        with self._lock:
            result = self._call('orders/'+order_id+'/submit',{})
            if result.get('ok'): self.refresh()
            return result

    def apply_referral(self, code):
        if not isinstance(code,str) or len(code.strip()) != 24:
            return {'ok':False,'error':'invalid_referral'}
        with self._lock:
            result = self._call('referral',{'code':code.strip()})
            if result.get('ok'): self.refresh()
            return result

    def logout(self):
        with self._lock:
            self._call('session/logout',{})
            self._token=''
            self._expires=0
            self._state.update(authenticated=False,active=False,orders=[],referral={},expires_at=None)
            return {'ok':True}
