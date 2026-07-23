from .models import SiteSettings


def site_globals(request):
    """把网站设置（联系方式、危机热线）注入所有模板。"""
    return {"site": SiteSettings.load()}
