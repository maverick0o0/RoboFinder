from requests.sessions import Session
from concurrent.futures import ThreadPoolExecutor
from threading import local
import signal,validators,re,datetime,argparse,time,requests
from urllib.parse import urlparse


class colors:
    PURPLE = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    WARNING_COLOR = '\033[93m'
    ERROR = '\033[91m'
    ENDC = '\033[0m'

class Logger_type:
    ERROR = 'Error'
    DEBUG = 'Debug'
    INFO = 'Info'


def logger(debug, message ,logger_type):
    current_time = datetime.datetime.now()
    formatted_time = current_time.strftime("%H:%M:%S")
    if debug == True:
        print(colors.CYAN + "[" + colors.WARNING_COLOR + logger_type + colors.CYAN + "][" + colors.ENDC + formatted_time + colors.CYAN + "] " + colors.ENDC + message)

def setup_argparse():
    parser = argparse.ArgumentParser(description="Robo Finder")
    parser.add_argument("--debug", action="store_true", default=False, help="enable debugging mode.")
    parser.add_argument('--url', '-u', dest='url', type=str, help='Give me the URL', required=True)
    parser.add_argument('--output', '-o', dest='output',default='', type=str, help='output file path.' ,required=False)
    parser.add_argument('--threads', '-t', dest='threads', default=10, type=int, help='number of threads to use.')
    parser.add_argument('-extract-path',action="store_true", default=False, help='Extract path separately and save it to $domain-path.txt .')
    parser.add_argument('-extract-params',action="store_true", default=False, help='Extract params separately and save it to $domain-params.txt .')
    parser.add_argument('-parse-url', '-utp', dest='utp', type=str, help='number of urls to parse.')
    parser.add_argument('-silent',action="store_true", default=False, help='stdout or not.')
    return parser.parse_args()

def extract(response):
    # Extract everything after Disallow and Allow
    pattern = r"(?:Disallow|Allow):\s*(.*)"
    matches = re.findall(pattern, response)
    result = '\n'.join(matches)

    # Remove '*', '//', and '_/'
    clean = re.sub(r"\*", "", result)
    clean = re.sub(r"\/\/", "", clean)
    clean = re.sub(r"_\/", "", clean)

    # Extract params
    extract_params_pattern = r"^\?([^=\n]*)|(?<=[?&])\w+(?==)|&([^=\n]*)"
    matched_params = re.finditer(extract_params_pattern, clean ,re.MULTILINE)
    params_list=[]
    
    for matchNum, match in enumerate(matched_params, start=1):
        params_list.append(match.group())
    
    # Remove special chars from begining of params 
    remove_special_chars_pattern = r'^[.&/\\()\[\]]+|\?'
    # params = re.sub(remove_special_chars_pattern, "", '\n'.join(params_list) , re.MULTILINE)
    params_list = [re.sub(remove_special_chars_pattern, "", element , re.MULTILINE) for element in params_list]

    
    # Extract path
    extract_path_pattern = r"^\/.*"
    path_list = re.findall(extract_path_pattern, clean, re.MULTILINE)
    
    
    return params_list, path_list


def get_all_links(args) -> list:
    logger(args.debug, "Sending an HTTP request to the archive to obtain all paths for robots.txt files." , Logger_type.DEBUG)
    try:
        obj = requests.get("https://web.archive.org/cdx/search/cdx?url={}/robots.txt&output=json&fl=timestamp,original&filter=statuscode:200&collapse=digest".format(args.url)).json()
    except:
        logger(True, "Failed to obtain data from the archive. Exiting...",Logger_type.ERROR)
        exit(1)
    url_list = []
    for i in obj:
        url_list.append("https://web.archive.org/web/{}if_/{}".format(i[0],i[1]))

    logger(args.debug, "Got the data as JSON objects.",Logger_type.DEBUG)
    logger(args.debug, "Requests count : {}".format(len(url_list)),Logger_type.DEBUG)
    
    if(len(url_list) > 500):
        logger(True, f"Requests count {len(url_list)} , it is recommended to set -utp number" , Logger_type.INFO)

    
    if "https://web.archive.org/web/timestampif_/original" in url_list:
        url_list.remove("https://web.archive.org/web/timestampif_/original")
    if len(url_list) == 0:
        logger(args.debug, "No robots.txt files found in the archive. Exiting...",Logger_type.DEBUG)
        exit(1)
    
    # How many URLs parse ( for site that has more than 2k results )
    if(args.utp != None):
        print(f"Requests count {len(url_list)} , processing {args.utp} URLs...")
        return url_list[:int(args.utp)]
    
    return url_list

# Define thread_local to prevent session confclits
thread_local = local()

def get_session() -> Session:
    if not hasattr(thread_local,'session'):
        thread_local.session = requests.Session()
    return thread_local.session

def concatinate(args,results) -> list:
    concatinated = []
    try:
        for i in results:
            if validators.url(i) != True:
                if i != "":
                    if i[0] == "/":
                        concatinated.append(args.url+i)
                    else:
                        concatinated.append(args.url+"/"+i)
            elif validators.url(i) == True:
                concatinated.append(i)
    except Exception as e:
        logger(args.debug, "Error occurred while concatinating paths. {}".format(e),Logger_type.ERROR)

    return concatinated
           
def fetchFiles(url:str):
    session = get_session()
    max_retries = 4
    retry_count = 0
    response = ""
    while retry_count < max_retries:
        try:
            response =  session.get(url)
            logger(args.debug, "HTTP Request Sent to {}".format(url),Logger_type.DEBUG)
            break

        except requests.exceptions.SSLError:
            time.sleep(1)
            logger(True, "Sending request again to {}".format(url) , Logger_type.ERROR)
            retry_count += 1
        except requests.exceptions.ConnectTimeout:
            logger(True, "Connecttion Timeout occurred. Retrying in 1 second..." ,Logger_type.ERROR)
            time.sleep(1)
            logger(True, "Sending request again to {}".format(url) , Logger_type.INFO)
            retry_count += 1

        except requests.exceptions.ConnectionError:
            logger(True, "ConnectionError occurred. Retrying in 1 second..." ,Logger_type.ERROR)
            time.sleep(1)
            logger(True, "Sending request again to {}".format(url),Logger_type.INFO)
            retry_count += 1

        except requests.exceptions.ChunkedEncodingError:
            logger(True, "ChunkedEncodingError occurred. Retrying in 5 seconds..." ,Logger_type.ERROR)
            time.sleep(5)
            logger(True, "Sending request again to {}".format(url),Logger_type.INFO)
            retry_count += 1

    return response

def handle_sigint(signal_number, stack_frame):
    print("Keyboard interrupt detected, stopping processing.")
    raise KeyboardInterrupt()

def startProccess(urls,args) -> list:
    signal.signal(signal.SIGINT, handle_sigint)
    responses = []
    logger(args.debug, "Sending a bunch of HTTP requests to fetch all robots.txt files.",Logger_type.DEBUG)
    try:
        with ThreadPoolExecutor(max_workers=args.threads) as executor:
            for resp in executor.map(fetchFiles,urls):
                if resp != "":
                    responses.append(resp.text)
    except KeyboardInterrupt:
        logger(args.debug,"Keyboard interrupt detected, stopping processing.",Logger_type.DEBUG)
        exit(1)
    return responses

args = setup_argparse()


def main():
    start = time.time()
    logger(args.debug, "Starting the program.",Logger_type.DEBUG)
    
    # Extract all old robots.txt URLs  
    url_list = get_all_links(args)
    
    # Send request to each URL and extract robots.txt content
    contents = startProccess(url_list,args)
    
    params = []
    path = []
    logger(args.debug, "Extracting all paths from robots.txt files.",Logger_type.DEBUG)
    end = time.time()
    logger(args.debug, "Time taken : {} seconds".format(end-start),Logger_type.DEBUG)
    for content in contents:
        params_array , path_array = extract(content)
        params = params + params_array
        path = path + path_array
        
    # Remove duplicates
    params = list(set(params))
    path = list(set(path))
    
    
    
    if len(path) == 0:
        logger(args.debug, "No paths found. Exiting...",Logger_type.DEBUG)
        exit(1)
    
    # Concatinate path with URL -> https://target.com/path
    logger(args.debug, "Concatinating paths with the site url.",Logger_type.DEBUG)
    concatinated_path = concatinate(args,path)
    
    # Extract and save path in $domain-path.txt 
    if args.extract_path == True:
        logger(args.debug, "Save path separately to $domain-path.txt .",Logger_type.DEBUG)
        domain = urlparse(args.url).netloc
        with open(f'{domain}-path.txt','w') as f:
            for i in path:
                try:
                    f.write(i.strip())
                    f.write('\n')
                except Exception as e:
                    print(f"Error {e}")
                    continue
        logger(args.debug, "Writing the path output to {} done.".format(args.output),Logger_type.DEBUG)
        
    # Extract and save params in $domain-params.txt 
    if args.extract_params == True:
        logger(args.debug, "Save params separately to $domain-params.txt .",Logger_type.DEBUG)
        domain = urlparse(args.url).netloc
        with open(f'{domain}-params.txt','w') as f:
            for i in params:
                try:
                    f.write(i.strip())
                    f.write('\n')
                except Exception as e:
                    print(f"Error {e}")
                    continue
                
        logger(args.debug, "Writing the params output to {} done.".format(args.output),Logger_type.DEBUG)
    
    logger(args.debug, "Total number of paths found : {}".format(len(path)),Logger_type.DEBUG)
    if args.output != '':
        with open(args.output,'w') as f:
            for i in concatinated_path:
                try:
                    f.write(i.strip())
                    f.write('\n')
                except Exception as e:
                    print(f"Error {e}")
                    continue
        logger(args.debug, "Writing the output to {} done.".format(args.output),Logger_type.DEBUG)
    if (args.silent == False):
        for i in concatinated_path:
            print(i)

if __name__ == "__main__":
    main()



# Todo
# Handle big request count ( split to smaller )