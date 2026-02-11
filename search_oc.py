import web
import os
import json
from src.wl import WebLogger
import requests
import urllib.parse as urlparse
import re
from urllib.parse import parse_qs
from rdflib.plugins.sparql.parser import parseUpdate
import subprocess
import sys
import argparse

# Load the configuration file
with open("conf.json") as f:
    c = json.load(f)


# Docker ENV variables
env_config = {
    "base_url": os.getenv("BASE_URL", c["base_url"]),
    "log_dir": os.getenv("LOG_DIR", c["log_dir"]),
    "sparql_endpoint": {
        "index": os.getenv("SPARQL_ENDPOINT_INDEX", c["sparql_endpoint"]["index"]),
        "meta": os.getenv("SPARQL_ENDPOINT_META", c["sparql_endpoint"]["meta"])
    },
    "sync_enabled": os.getenv("SYNC_ENABLED", "false").lower() == "true"
}


active = {
    "corpus": "datasets",
    "index": "datasets",
    "meta": "datasets",
    "coci": "datasets",
    "doci": "datasets",
    "poci": "datasets",
    "croci": "datasets",
    "ccc": "datasets",
    "oci": "tools",
    "intrepid": "tools",
    "api": "querying",
    "sparql": "querying",
    "search": "querying"
}

# URL Mapping
urls = (
    "/", "Main",
    "/static/(.*)", "Static",
    "/sparql/index", "SparqlIndex",  # Add specific endpoint routes
    "/sparql/meta", "SparqlMeta",
    '/search', 'Search',
    '/favicon.ico', 'Favicon'
)

# Set the web logger
# web_logger = WebLogger(env_config["base_url"], env_config["log_dir"], [
#     "HTTP_X_FORWARDED_FOR", # The IP address of the client
#     "REMOTE_ADDR",          # The IP address of internal balancer
#     "HTTP_USER_AGENT",      # The browser type of the visitor
#     "HTTP_REFERER",         # The URL of the page that called your program
#     "HTTP_HOST",            # The hostname of the page being attempted
#     "REQUEST_URI",          # The interpreted pathname of the requested document
#                             # or CGI (relative to the document root)
#     "HTTP_AUTHORIZATION",   # Access token
#     ],
#     # comment this line only for test purposes
#      {"REMOTE_ADDR": ["130.136.130.1", "130.136.2.47", "127.0.0.1"]}
# )

render = web.template.render(c["html"], globals={
    'str': str,
    'isinstance': isinstance,
    'render': lambda *args, **kwargs: render(*args, **kwargs),
    'web': web
})

# App Web.py
app = web.application(urls, globals())

# WSGI application for Gunicorn
application = app.wsgifunc()

def sync_static_files():
    """
    Function to synchronize static files using sync_static.py
    """
    try:
        print("Starting static files synchronization...")
        subprocess.run([sys.executable, "sync_static.py", "--auto"], check=True)
        print("Static files synchronization completed")
    except subprocess.CalledProcessError as e:
        print(f"Error during static files synchronization: {e}")
    except Exception as e:
        print(f"Unexpected error during synchronization: {e}")


# Process favicon.ico requests
class Favicon:
    def GET(self):
        is_https = (
            web.ctx.env.get('HTTP_X_FORWARDED_PROTO') == 'https' or
            web.ctx.env.get('HTTPS') == 'on' or
            web.ctx.env.get('SERVER_PORT') == '443'
        )
        protocol = 'https' if is_https else 'http'
        raise web.seeother(f"{protocol}://{web.ctx.host}/static/favicon.ico")
    
class Static:
    def GET(self, name):
        """Serve static files"""
        static_dir = "static"
        file_path = os.path.join(static_dir, name)

        if not os.path.exists(file_path):
            raise web.notfound()

        # Content types
        ext = os.path.splitext(name)[1]
        content_types = {
            '.css': 'text/css',
            '.js': 'application/javascript',
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.gif': 'image/gif',
            '.svg': 'image/svg+xml',
            '.ico': 'image/x-icon',
            '.woff': 'font/woff',
            '.woff2': 'font/woff2',
            '.ttf': 'font/ttf',
        }

        web.header('Content-Type', content_types.get(ext, 'application/octet-stream'))

        with open(file_path, 'rb') as f:
            return f.read()

class Header:
    def GET(self):
        current_subdomain = web.ctx.host.split('.')[0].lower()
        return render.header(sp_title="", current_subdomain=current_subdomain)

class Sparql:
    def __init__(self, sparql_endpoint, sparql_endpoint_title, yasqe_sparql_endpoint):
        self.sparql_endpoint = sparql_endpoint
        self.sparql_endpoint_title = sparql_endpoint_title
        self.yasqe_sparql_endpoint = yasqe_sparql_endpoint
        self.collparam = ["query"]

    def GET(self):
        # web_logger.mes()
        content_type = web.ctx.env.get('CONTENT_TYPE')
        return self.__run_query_string(self.sparql_endpoint_title, web.ctx.env.get("QUERY_STRING"), content_type)

    def POST(self):
        content_type = web.ctx.env.get('CONTENT_TYPE')
        cur_data = web.data().decode("utf-8")

        if "application/x-www-form-urlencoded" in content_type:
            return self.__run_query_string(active["sparql"], cur_data, True, content_type)
        elif "application/sparql-query" in content_type:
            isupdate = None
            isupdate, sanitizedQuery = self.__is_update_query(cur_data)
            if not isupdate:
                return self.__contact_tp(cur_data, True, content_type)
            else:
                raise web.HTTPError(
                    "403 ",
                    {"Content-Type": "text/plain"},
                    "SPARQL Update queries are not permitted."
                )
        else:
            raise web.redirect("/")

    def __contact_tp(self, data, is_post, content_type):
        accept = web.ctx.env.get('HTTP_ACCEPT')
        if accept is None or accept == "*/*" or accept == "":
            accept = "application/sparql-results+xml"
        
        # Add debug logging
        print(f"Contacting endpoint: {self.sparql_endpoint}")
        print(f"Request type: {'POST' if is_post else 'GET'}")
        print(f"Headers: Content-Type={content_type}, Accept={accept}")
        
        try:
            if is_post:
                req = requests.post(self.sparql_endpoint, 
                                  data=data,
                                  headers={'content-type': content_type, 
                                         'accept': accept})
            else:
                req = requests.get(f"{self.sparql_endpoint}?{data}",
                                 headers={'content-type': content_type, 
                                        'accept': accept})
            
            print(f"Response status: {req.status_code}")
            
            if req.status_code == 200:
                web.header('Access-Control-Allow-Origin', '*')
                web.header('Access-Control-Allow-Credentials', 'true')
                web.header('Content-Type', req.headers["content-type"])
                # web_logger.mes()
                req.encoding = "utf-8"
                return req.text
            else:
                print(f"Error response: {req.text}")
                raise web.HTTPError(
                    f"{req.status_code} ",
                    {"Content-Type": req.headers["content-type"]},
                    req.text
                )
        except requests.exceptions.RequestException as e:
            print(f"Request error: {str(e)}")
            raise web.HTTPError(
                "503 ",
                {"Content-Type": "text/plain"},
                f"Error contacting SPARQL endpoint: {str(e)}"
            )

    def __is_update_query(self, query):
        query = re.sub(r'^\s*#.*$', '', query, flags=re.MULTILINE)
        query = '\n'.join(line for line in query.splitlines() if line.strip()) 
        try:
            parseUpdate(query)
            return True, 'UPDATE query not allowed'
        except Exception:
            return False, query

    def __run_query_string(self, active, query_string, is_post=False,
                          content_type="application/x-www-form-urlencoded"):
        parsed_query = urlparse.parse_qs(query_string)
        current_subdomain = web.ctx.host.split('.')[0].lower()
        if query_string is None or query_string.strip() == "":
            # web_logger.mes()
            return getattr(render, self.sparql_endpoint_title)(
                active=active, 
                sp_title=self.sparql_endpoint_title, 
                sparql_endpoint=self.yasqe_sparql_endpoint, 
                render=render,
                current_subdomain=current_subdomain)
        for k in self.collparam:
            if k in parsed_query:
                query = parsed_query[k][0]
                isupdate = None
                isupdate, sanitizedQuery = self.__is_update_query(query)

                if isupdate != None:
                    if isupdate:
                        raise web.HTTPError(
                            "403 ",
                            {"Content-Type": "text/plain"},
                            "SPARQL Update queries are not permitted."
                        )
                    else:
                        return self.__contact_tp(query_string, is_post, content_type)

        raise web.HTTPError(
            "408",
            {"Content-Type": "text/plain"},
            "Not a valid request"
        )

class Main:
    def GET(self):
        # web_logger.mes()
        current_subdomain = web.ctx.host.split('.')[0].lower()
        sparql_endpoint_meta= env_config["sparql_endpoint"]["meta"]
        sparql_endpoint_index= env_config["sparql_endpoint"]["index"]
        return render.search(
            active="", 
            sp_title="", 
            sparql_endpoint="", 
            sparql_endpoint_meta=sparql_endpoint_meta,
            sparql_endpoint_index=sparql_endpoint_index,
            query_string="", 
            current_subdomain=current_subdomain, 
            render=render
        )


class SparqlEndpoint(Sparql):
    def __init__(self,value):
        Sparql.__init__(self, value,
                       "sparql endpoint", "/sparql")

class SparqlIndex(Sparql):
    def __init__(self):
        Sparql.__init__(self, 
                       env_config["sparql_endpoint"]["index"],
                       "sparql index", 
                       "/sparql/index")

class SparqlMeta(Sparql):
    def __init__(self):
        Sparql.__init__(self, 
                       env_config["sparql_endpoint"]["meta"],
                       "sparql meta", 
                       "/sparql/meta")

class Search:
    def GET(self):
        # web_logger.mes()
        current_subdomain = web.ctx.host.split('.')[0].lower()
        query = web.input(text="", rule="citingdoi")  # rule default a citingdoi
        sparql_endpoint_json = json.dumps(env_config["sparql_endpoint"])
        return render.search(
            active="", 
            sp_title="", 
            sparql_endpoint=sparql_endpoint_json, 
            sparql_endpoint_meta=env_config["sparql_endpoint"]["meta"],
            sparql_endpoint_index=env_config["sparql_endpoint"]["index"],
            query_string=f"text={query.text}&rule={query.rule}", 
            current_subdomain=current_subdomain, 
            render=render
        )

# Run the application on localhost for development/testing
if __name__ == "__main__":
    # Add startup log
    print("Starting SEARCH OpenCitations web application...")
    print(f"Configuration: Base URL={env_config['base_url']}")
    print(f"Sync enabled: {env_config['sync_enabled']}")
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='SEARCH OpenCitations web application')
    parser.add_argument(
        '--sync-static',
        action='store_true',
        help='synchronize static files at startup (for local testing or development)'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=8080,
        help='port to run the application on (default: 8080)'
    )
    
    args = parser.parse_args()
    print(f"Starting on port: {args.port}")
    
    if args.sync_static or env_config["sync_enabled"]:
        # Run sync if either --sync-static is provided (local testing) 
        # or sync_enabled=true (Docker environment)
        print("Static sync is enabled")
        sync_static_files()
    else:
        print("Static sync is disabled")
    
    print("Starting web server...")
    # Set the port for web.py
    web.httpserver.runsimple(app.wsgifunc(), ("0.0.0.0", args.port))