# 2013.06.22 09:23:40 PDT
from importlib import import_module
from functools import wraps
from django.http import HttpResponse
from django.utils import simplejson
from django.forms.models import model_to_dict
from decimal import Decimal
import datetime
from django.db import models
import logging
logger = logging.getLogger(__name__)

class HttpInterrupt(Exception):
    """
        Raise when req/resp cycle should end early and serve response
    
        ie: If an authorization fails, we can stop the pipeline
        and serve an error message
        """


    def __init__(self, response):
        self.response = response or HttpResponse('No content')




def subscribe(sub = None):
    """
        Runs the wrapped method if sub matches any pub namespaces
    
        ie: "if any"
        """

    def func_wrapper(func):

        @wraps(func)
        def returned_wrapper(self, request, *args, **kwargs):
            for name in sub:
                if name in kwargs['pub']:
                    return func(self, request, *args, **kwargs)

            return (request, args, kwargs)


        return returned_wrapper


    return func_wrapper



def avoid(avoid = None):
    """
        Avoids running the method if any avoid string matches a pub
    
        ie: "if none of these"
        """

    def func_wrapper(func):

        @wraps(func)
        def returned_wrapper(self, request, *args, **kwargs):
            for name in avoid:
                if name in kwargs['pub']:
                    return (request, args, kwargs)

            return func(self, request, *args, **kwargs)


        return returned_wrapper


    return func_wrapper



def match(match = None):
    """
        Runs the wrapped method if we match all the sub words
    
        ie: "if and only if all of these"
        """

    def func_wrapper(func):

        @wraps(func)
        def returned_wrapper(self, request, *args, **kwargs):
            for name in match:
                if name not in kwargs['pub']:
                    return (request, args, kwargs)

            return func(self, request, *args, **kwargs)


        return returned_wrapper


    return func_wrapper



class Pipeline(object):
    """
    Runs a request through a pipeline and returns a response
    """


    def _get_method(self, method_string):
        method = getattr(self.__class__, method_string, None)
        if not method:
            pieces = method_string.split('.')
            if len(pieces) < 2:
                raise Exception('No such method found: {0}'.format(method_string))
            module = '.'.join(pieces[:-2])
            (cls, method,) = (pieces[-2], pieces[-1])
            module = import_module(module)
            cls = getattr(module, cls)
            method = getattr(cls, method)
        return method



    @classmethod
    def as_view(cls):
        """
        Returns a function for processing request response cycle
        """

        def view(request, *args, **kwargs):
            """
            Process the request, return a response
            """
            self = cls()
            for method_string in self.pipeline[:-1]:
                method = self._get_method(method_string)
                try:
                    (request, args, kwargs,) = method(self, request, *args, **kwargs)
                except HttpInterrupt as e:
                    return e.response

            response_method = self._get_method(self.pipeline[-1])
            return response_method(self, request, *args, **kwargs)


        return view




class ModelResource(Pipeline):
    """
    RESTful api resource
    """

    pipeline = ('build_pub', 'get_object_from_kwargs', 'json_to_python', 'check_permissions', 'get_detail', 'get_list', 'post_detail', 'post_list', 'put_detail', 'put_list', 'delete_detail', 'delete_list', 'objs_to_bundles', 'produce_response_data', 'serialize_response_data', 'response')
    pk_field = 'pk'
    limit = 20
    field_dehydrate = ('name', 'dehydrate_name')

    def __init__(self, *args, **kwargs):
        super(ModelResource, self).__init__(*args, **kwargs)



    def forbidden(self):
        response = HttpResponse('', status=403, content_type='application/json')
        raise HttpInterrupt(response)



    def _update_from_dict(self, instance, data):
        instance.__dict__.update(data)
        return instance



    def build_pub(self, request, *args, **kwargs):
        """
        Builds a list of keywords relevant to this request
        """
        pub = []
        pub.append(request.method.lower())
        if kwargs.get(self.pk_field, None):
            pub.append('detail')
        else:
            pub.append('list')
        kwargs['pub'] = pub
        return (request, args, kwargs)



    @subscribe(sub=['detail'])
    def get_object_from_kwargs(self, request, *args, **kwargs):
        """
        Retrieve instance of model referenced by url kwargs
        """
        cls = self.Meta.model
        try:
            instance = cls.objects.get(pk=kwargs['pk'])
        except cls.DoesNotExist:
            response = HttpResponse('Object does not exist', status=404, content_type='application/json')
            raise HttpInterrupt(response)
        kwargs['instance'] = instance
        return (request, args, kwargs)



    def check_permissions(self, request, *args, **kwargs):
        return (request, args, kwargs)



    @subscribe(sub=['post', 'put'])
    def json_to_python(self, request, *args, **kwargs):
        if request.body:
            data = request.body
            kwargs['request_data'] = simplejson.loads(data)
        return (request, args, kwargs)



    @subscribe(sub=['post', 'put'])
    def hydrate_request_data(self, request, *args, **kwargs):
        hydrated_data = {}
        for (fieldname, fieldvalue,) in kwargs['request_data']:
            model_field = getattr(kwargs['instance'], fieldname, None)




    @match(match=['get', 'detail'])
    def get_detail(self, request, *args, **kwargs):
        kwargs['status'] = 200
        return (request, args, kwargs)



    @match(match=['get', 'list'])
    def get_list(self, request, *args, **kwargs):
        cls = self.Meta.model
        total_instances = cls.objects.all()
        limit_instances = total_instances[:self.limit]
        kwargs['objs'] = limit_instances
        kwargs['meta'] = {'total': total_instances.count(),
         'limit': self.limit}
        kwargs['status'] = 200
        return (request, args, kwargs)



    @match(match=['put', 'detail'])
    def put_detail(self, request, *args, **kwargs):
        instance = self._update_from_dict(kwargs['instance'], kwargs['request_data'])
        instance.save()
        kwargs['instance'] = instance
        kwargs['status'] = 201
        return (request, args, kwargs)



    @match(match=['post', 'list'])
    def post_list(self, request, *args, **kwargs):
        instance = self.Meta.model()
        instance = self._update_from_dict(instance, kwargs['request_data'])
        instance.save()
        kwargs['instance'] = instance
        kwargs['status'] = 201
        return (request, args, kwargs)



    @match(match=['detail', 'delete'])
    def delete_detail(self, request, *args, **kwargs):
        instance = kwargs['instance']
        del kwargs['instance']
        instance.delete()
        kwargs['response'] = ''
        kwargs['status'] = 204
        return (request, args, kwargs)



    @match(match=['put', 'list'])
    def put_list(self, request, *args, **kwargs):
        kwargs['status'] = 501
        return (request, args, kwargs)



    @match(match=['post', 'detail'])
    def post_detail(self, request, *args, **kwargs):
        kwargs['status'] = 501
        return (request, args, kwargs)



    @match(match=['delete', 'list'])
    def delete_list(self, request, *args, **kwargs):
        kwargs['status'] = 501
        return (request, args, kwargs)



    @avoid(avoid=['delete'])
    def objs_to_bundles(self, request, *args, **kwargs):
        """
        Convert object fields to serializable data types
        """
        if kwargs.get('instance', None):
            objs = [kwargs['instance']]
        elif kwargs.get('objs', None):
            objs = kwargs['objs']
        else:
            objs = []
        bundles = []
        for obj in objs:
            obj_data = {}
            for field in obj._meta.fields:
                dehydrated_value = self._to_basic_type(obj, field)
                obj_data[field.name] = dehydrated_value

            bundles.append({'obj': obj,
             'data': obj_data})

        kwargs['bundles'] = bundles
        return (request, args, kwargs)



    def _to_basic_type(self, obj, field):
        """
        Convert complex data types into serializable types
        """
        if isinstance(field, models.AutoField):
            return field.value_from_object(obj)
        if isinstance(field, models.BooleanField):
            return field.value_from_object(obj)
        if isinstance(field, models.CharField):
            return field.value_from_object(obj)
        if isinstance(field, models.TextField):
            return field.value_from_object(obj)
        if isinstance(field, models.IntegerField):
            return field.value_from_object(obj)
        if isinstance(field, models.FloatField):
            return field.value_from_object(obj)
        if isinstance(field, models.FileField):
            return field.value_to_string(obj)
        if isinstance(field, models.ImageField):
            return field.value_to_string(obj)
        if isinstance(field, models.DateTimeField):
            return field.value_to_string(obj)
        if isinstance(field, models.DateField):
            return field.value_to_string(obj)
        if isinstance(field, models.DecimalField):
            return field.value_to_string(obj)
        if isinstance(field, models.ForeignKey):
            return field.value_from_object(obj)
        if isinstance(field, models.ManyToManyField):
            return eval(field.value_to_string(obj))
        return 
        logger.info('Could not find field type match for {0}'.format(field))



    @avoid(avoid=['delete'])
    def produce_response_data(self, request, *args, **kwargs):
        data_dicts = []
        for bundle in kwargs['bundles']:
            data_dicts.append(bundle['data'])

        if 'detail' in kwargs['pub']:
            kwargs['response_data'] = data_dicts[0]
        else:
            kwargs['response_data'] = {'meta': kwargs['meta'],
             'objects': data_dicts}
        return (request, args, kwargs)



    def serialize_response_data(self, request, *args, **kwargs):
        response = kwargs.get('response_data', None)
        kwargs['serialized'] = simplejson.dumps(response)
        return (request, args, kwargs)



    def response(self, request, *args, **kwargs):
        return HttpResponse(kwargs['serialized'], status=kwargs['status'], content_type='application/json')




+++ okay decompyling pipeline.pyc 
# decompiled 1 files: 1 okay, 0 failed, 0 verify failed
# 2013.06.22 09:23:41 PDT