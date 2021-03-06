#####################################################################

import json
from django.shortcuts import get_object_or_404, render, render_to_response
from django.http import HttpResponseRedirect, HttpResponse
from django.core.urlresolvers import reverse
from django.views import generic
from crickets.models import *
from django.core import serializers
from django.template import Context, loader, RequestContext
from itertools import chain
from django.db.models import Count

# todo move forms
from django import forms
from django.forms import ModelForm

from django.contrib.auth.models import User
from django import forms

from django.contrib.auth import authenticate, login, logout


#####################################################################
## index

class IndexView(generic.ListView):
    template_name = 'crickets/index.html'
    context_object_name = 'crickets_list'
    def get_queryset(self):
        return Cricket.objects.exclude(num_videos=0).order_by('?')[:5]

    def get_context_data(self, **kwargs):
        context = super(IndexView, self).get_context_data(**kwargs)
        context['burrows'] = Burrow.objects.all()
        context['hiscores_list']=Event.objects.all()\
                            .exclude(user__isnull=True)\
                            .values('user__username')\
                            .annotate(count=Count('user'))\
                            .order_by('-count')[:20]

        return context

######################################################################
## player page

class PlayerView(generic.DetailView):
    model = User
    template_name = 'crickets/player.html'

    def get_context_data(self, **kwargs):
        context = super(PlayerView, self).get_context_data(**kwargs)

        ###############################################################
        ## long lookup via all events (add movie.m.* to template to use)
        ## get all unique movies that contain events we've tagged
        #context['movies']=Event.objects.filter(user=context["user"]).values("movie").distinct()
        ## lookup the movies themselves
        ## this should be done in SQL - wtf can't work out how with ORM
        #for movie in context['movies']:
        #    movie["m"] = Movie.objects.get(pk=movie["movie"])

        ###############################################################
        ## fast lookup via playerstomovies
        context['movies']=PlayersToMovies.objects.filter(user=context["user"])



        return context

######################################################################
## cricket page

class CricketView(generic.DetailView):
    model = Cricket
    template_name = 'crickets/cricket.html'

    def get_context_data(self, **kwargs):
        context = super(CricketView, self).get_context_data(**kwargs)
        context['least_watched_movies']=Movie.objects.filter(cricket=context['cricket']).exclude(status=0).order_by('views')[:30]

        for movie in context['least_watched_movies']:
            movie.contributors=Event.objects.filter(movie=movie)\
                            .exclude(user__isnull=True)\
                            .values('user__username')\
                            .annotate(count=Count('user'))\
                            .count()

        context['most_interesting_movies']=Movie.objects.filter(cricket=context['cricket']).exclude(status=0).order_by('-num_events')[:30]

        for movie in context['most_interesting_movies']:
            movie.contributors=Event.objects.filter(movie=movie)\
                            .exclude(user__isnull=True)\
                            .values('user__username')\
                            .annotate(count=Count('user'))\
                            .count()

        context['num_events']=Event.objects.filter(movie__cricket=context['cricket']).count()

        context['fan_list']=Event.objects.filter(movie__cricket=context['cricket'])\
                            .exclude(user__isnull=True)\
                            .values('user__username')\
                            .annotate(count=Count('user'))\
                            .order_by('-count')[:3]

        context['anon']=Event.objects.filter(movie__cricket=context['cricket'], user__isnull=True).count()
        context['total_videos']=Movie.objects.filter(cricket=context['cricket']).count()
        context['total_videos_ready']=Movie.objects.filter(cricket=context['cricket']).exclude(status=0).count()
        context['total_hours']="%0.2f"%(context['total_videos']/120.0)
        return context

# just like cricket view atm
class BurrowView(generic.DetailView):
    model = Burrow
    template_name = 'crickets/burrow.html'

    def get_context_data(self, **kwargs):
        context = super(BurrowView, self).get_context_data(**kwargs)
        context['least_watched_movies']=Movie.objects.filter(burrow=context['burrow']).exclude(status=0).order_by('views')[:30]
        for movie in context['least_watched_movies']:
            movie.contributors=Event.objects.filter(movie=movie)\
                            .exclude(user__isnull=True)\
                            .values('user__username')\
                            .annotate(count=Count('user'))\
                            .count()

        context['most_interesting_movies']=Movie.objects.filter(burrow=context['burrow']).exclude(status=0).order_by('-num_events')[:30]
        for movie in context['most_interesting_movies']:
            movie.contributors=Event.objects.filter(movie=movie)\
                            .exclude(user__isnull=True)\
                            .values('user__username')\
                            .annotate(count=Count('user'))\
                            .count()

        context['total_videos']=Movie.objects.filter(burrow=context['burrow']).count()
        context['total_videos_ready']=Movie.objects.filter(burrow=context['burrow'])\
                                                   .exclude(status=0)\
                                                   .count()
        context['total_hours']="%0.2f"%(context['total_videos']/120.0)
        return context


######################################################################
## movie page

class MovieView(generic.DetailView):
    model = Movie
    template_name = 'crickets/movie.html'

    def get_context_data(self, **kwargs):
        context = super(MovieView, self).get_context_data(**kwargs)

        # inc views
        context['movie'].views+=1
        context['movie'].save()

        context['event_types']=EventType.objects.all()
        for c, event_type in enumerate(context['event_types']):
            event_type.width=int(100/len(context['event_types']))*0.5

        context['events']=Event.objects.filter(movie=context['movie'])
        context['buttons'] = [1, 2, 3, 4, 5, 6, 7]
        context['predator_bird'] = EventType.objects.filter(name="Predator: Bird").first()
        context['predator_shrew'] = EventType.objects.filter(name="Predator: Shrew").first()
        context['something_else'] = EventType.objects.filter(name="Something Else").first()
        return context

class EventForm(ModelForm):
     class Meta:
         model = Event
         fields = "__all__" 

## incoming from javascript...
def spit_event(request):
    if request.method == 'POST':
        form = EventForm(request.POST)
        if form.is_valid():
            form.save()
            # update the stats for this player
            # too much here???
            # either this or a laggy continual robot.py process
            data = form.cleaned_data

            # if we're not anonymous
            if data["user"]:
                profile = data["user"].profile
                profile.num_events+=1
                profile.save()

                user = data["user"]
                movie = data["movie"]

                try:
                    existing = PlayersToMovies.objects.get(user=user,movie=movie)
                except PlayersToMovies.DoesNotExist:
                    print("Player to movie added for "+user.username)
                    PlayersToMovies(user=user, movie=movie).save()

            return HttpResponse('')
        return HttpResponse('request is invalid: '+str(form))
    else:
        form = EventForm()
        return render(request, 'crickets/event.html', {'form': form})

######################################################################
## user stuff

class UserForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput())

    class Meta:
        model = User
        fields = ('username', 'email', 'password')

class UserProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ('picture',)

def register(request):
    context = RequestContext(request)
    registered = False

    if request.method == 'POST':
        user_form = UserForm(data=request.POST)
        profile_form = UserProfileForm(data=request.POST)

        if user_form.is_valid() and profile_form.is_valid():
            user = user_form.save()
            user.set_password(user.password)
            user.save()
            profile = profile_form.save(commit=False)
            profile.user = user
            if 'picture' in request.FILES:
                profile.picture = request.FILES['picture']
            profile.save()
            registered = True
        else:
            print user_form.errors, profile_form.errors
    else:
        user_form = UserForm()
        profile_form = UserProfileForm()

    return render_to_response(
            'crickets/register.html',
            {'user_form': user_form, 'profile_form': profile_form, 'registered': registered},
            context)

def logmein(request):
    context = RequestContext(request)

    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
        user = authenticate(username=username, password=password)
        if user:
            if user.is_active:
                login(request, user)
                return HttpResponseRedirect('/')
            else:
                return HttpResponse("Your account is disabled.")
        else:
            print "Invalid login details: {0}, {1}".format(username, password)
            return HttpResponse("Invalid login details supplied.")

    else:
        return render_to_response('crickets/login.html', {}, context)



def logmeout(request):
    logout(request)
    return HttpResponseRedirect('/')

# redirect to a random movie
def random_movie(request):
    return HttpResponseRedirect('/movie/'+str(random_one_check_status(Movie,1).pk))

######################################################################
## json data

def suck(request):
    data = serializers.serialize("json", Cricket.objects.all())
    return HttpResponse(json.dumps(data), content_type="application/json")

def spit(request):
    pass
