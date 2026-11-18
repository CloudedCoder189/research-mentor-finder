import asyncio
import os
from fastapi import APIRouter, Depends, HTTPException, Request, Response, Query
from pydantic import BaseModel, ConfigDict, field_validator
from api.auth.dependencies import AuthenticatedUser, require_user
from api import usage

router=APIRouter(prefix='/api/usage',tags=['usage'])


class PageView(BaseModel):
    model_config=ConfigDict(extra='forbid')
    page: str

    @field_validator('page')
    @classmethod
    def known_page(cls,value):
        if value not in usage.PAGES:
            raise ValueError('Unknown page category')
        return value


@router.post('/pageview',status_code=204)
async def pageview(payload:PageView, request:Request):
    if not usage.enabled() or request.headers.get('dnt')=='1' or request.headers.get('sec-gpc')=='1':
        return Response(status_code=204)
    origins={s.strip().rstrip('/') for s in os.getenv('CORS_ORIGINS','').split(',') if s.strip()}
    if request.headers.get('origin','').rstrip('/') not in origins:
        raise HTTPException(403,'Same-origin page views only')
    await asyncio.to_thread(usage.increment, 'page:'+payload.page)
    return Response(status_code=204)


@router.get('/summary')
def summary(days:int=Query(default=30,ge=1,le=90),user:AuthenticatedUser=Depends(require_user)):
    if not usage.admin_email(user.email,user.user_id):
        raise HTTPException(403,'Usage reports are restricted to the project owner.')
    return usage.report(days)


@router.get('/access')
def access(user:AuthenticatedUser=Depends(require_user)):
    return {'allowed':usage.admin_email(user.email,user.user_id)}
