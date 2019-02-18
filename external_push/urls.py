from django.conf.urls import url
from django.contrib import admin

from django.conf import settings
from django.conf.urls.static import static

import external_push.views


# This gets added to the app's urlpatterns
# TODO - Convert this to be properly namespaced
external_push_urlpatterns = [
    ## External Push Views
    url(r'^push/$', external_push.views.external_push_list, name='external_push_list'),
    url(r'^push/add/$', external_push.views.external_push_generic_target_add, name='external_push_generic_target_add'),
    url(r'^push/view/(?P<push_target_id>[0-9]{1,20})/$', external_push.views.external_push_view, name='external_push_view'),
    url(r'^push/delete/(?P<push_target_id>[0-9]{1,20})/$', external_push.views.external_push_delete, name='external_push_delete'),

]
