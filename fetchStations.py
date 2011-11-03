from google.appengine.ext import webapp
from google.appengine.ext.deferred.deferred import PermanentTaskFailure
from google.appengine.api import memcache, urlfetch, mail, users, app_identity
from google.appengine.ext.webapp.util import run_wsgi_app
from django.utils import simplejson
from BeautifulSoup import *
import logging, re
from station import *

class FetchStations(webapp.RequestHandler):

    def get(self):
        logging.error('Task begin')
        try:
            result = urlfetch.fetch('http://www.vcub.fr/stations/plan', deadline = 10)
        except urlfetch.DownloadError:
            logging.error('Timeout')
            self.error(200)
            return
        if result.status_code != 200:
            logging.error(
                'Unable to reach list webservice, error '
                + str(result.status_code))
            self.error(200)
            return
        pattern = re.compile('\"markers\": (\[.*\])')
        match = pattern.search(result.content)
        result = match.group(1).decode('utf8').replace(u'\\x3e', '')
        result = result.replace(u'\\x3c', '')
        result = result.replace(u'\\\'', '\'')
        json_stations = simplejson.loads(result)
        stations = get_stations()
        new_stations = []
        parsed_ids = set()
        if stations is None:
            stations = {}
        for json_station in json_stations:
            text = json_station.get('text')
            id = int(re.compile('#(\d+)').search(text).group(1))
            parsed_ids.add(id)
            slots_search = re.compile('strong(\d+)/strong p').search(text)
            open = True
            if slots_search is not None:
                slots = int(slots_search.group(1))
                bikes = int(re.compile('strong(\d+)/strong v').search(text).group(1))
            else:
                open = False
            station = stations.get(id)
            if station is not None:
                logging.error(station)
                station.open = open
                station.freeSlots = slots
                station.availableBikes = bikes
            else:
                cb = True
                if re.compile('title=\"Carte Bancaire\"').search(text) is None:
                    cb = False
                special = False
                if re.compile('vcub\+').search(json_station.get('markername')) is not None:
                    special = True
                new_station = Station(id = id, 
                        name = re.compile('#\d+ *- *(.+)/div').search(text).group(1),
                        address = re.compile('\"gmap-adresse\"(.+)/div').search(text).group(1).title(),
                        open = open,
                        payment = cb,
                        special = special,
                        network = 1,
                        latitude = float(json_station.get('latitude')),
                        longitude = float(json_station.get('longitude')),
                        availableBikes = bikes,
                        freeSlots = slots)
                new_stations.append(new_station)
                stations[id] = new_station
        if len(new_stations) != 0:
            logging.error('saving to db')
            db.put(new_stations)
        to_remove = set(stations.keys()).difference(parsed_ids)
        for id in to_remove:
            station = stations.pop(id)
            logging.error('removing id ' + str(id) + ' is saved ' + str(station.is_saved()))
            station.delete()
        memcache.set('stations', stations)
        self.response.out.write("<html><body><p>OK</p></body></html>")