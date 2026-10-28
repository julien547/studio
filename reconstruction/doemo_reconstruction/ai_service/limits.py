"""Bound private JSON uploads before framework parsing, including chunked bodies."""
class BodyLimit:
    def __init__(self,app,limit=13*1024**2):self.app,self.limit=app,limit
    async def __call__(self,scope,receive,send):
        if scope['type']!='http' or scope.get('method') not in ('POST','PUT','PATCH'):
            return await self.app(scope,receive,send)
        body=bytearray()
        while True:
            message=await receive()
            if message['type']=='http.disconnect':return
            chunk=message.get('body',b'')
            if len(body)+len(chunk)>self.limit:
                await send({'type':'http.response.start','status':413,'headers':[(b'content-type',b'text/plain')]})
                await send({'type':'http.response.body','body':b'Request too large'});return
            body.extend(chunk)
            if not message.get('more_body',False):break
        sent=False
        async def replay():
            nonlocal sent
            if not sent:
                sent=True;return {'type':'http.request','body':bytes(body),'more_body':False}
            return await receive()
        await self.app(scope,replay,send)
