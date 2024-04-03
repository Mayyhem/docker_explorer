import json
import subprocess
import docker
import time
import os

from sys import platform
from requests import request
from utils.Log import getLogger
LOG = getLogger(__name__)

def scan_image(tagged_image:str, tmp_path:str, whispers_config:str, whispers_output:str, whispers_timeout:int, completedtagsfile:str):
    LOG.debug(f"Image: {tagged_image}")
    container_name= "explore_"+tagged_image.replace("/", "_").replace(":", "-")
    container_exists = False

    try:
        client = docker.from_env()

        # Check if container with the same name already exists
        existing_containers = client.containers.list(all=True)
        for container in existing_containers:
            if container.name == container_name:
                container_exists = True
                LOG.debug(f"Container with the name {container_name} already exists. Skipping.")
                break

        if not container_exists:
            LOG.debug(f"Pull image: {tagged_image}")
            image= client.images.pull(f"{tagged_image}")
            
            LOG.debug(f"Create container: {container_name}")
            container= client.containers.create(image=f"{tagged_image}", command="fake_command", name=container_name)

            LOG.debug(f"Export fs: {tagged_image}")
            tmp_dump= os.path.join(tmp_path, container_name)
            export = subprocess.run(f"docker export {container_name} -o {tmp_dump}.tar", shell=True, stdout=subprocess.PIPE, text=True)

            LOG.debug(f"Remove container: {container_name}")
            container.remove()

            LOG.debug(f"Untar: {tagged_image}")
            mkdir = subprocess.run(f"mkdir {tmp_dump}", shell=True, stdout=subprocess.PIPE, text=True, check=True)
            untar = subprocess.run(f"tar -xf {tmp_dump}.tar -C {tmp_dump}", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

            LOG.debug(f"Whispers: {tagged_image}")
            start = time.time()
            try:
                output_dir= os.path.join(whispers_output, container_name)
                if platform == "linux" or platform == "linux2":
                    # In linux it can be used the shell command `timeout` to limit Whispers execution
                    if whispers_config:
                        whispers = subprocess.run(f"timeout {whispers_timeout} whispers -d {output_dir} -c {whispers_config} {tmp_dump}", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    else:
                        whispers = subprocess.run(f"timeout {whispers_timeout} whispers -d {output_dir} {tmp_dump}", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                else:
                    if whispers_config:
                        whispers = subprocess.run(f"whispers -d {output_dir} -c {whispers_config} {tmp_dump}", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    else:
                        whispers = subprocess.run(f"whispers -d {output_dir} {tmp_dump}", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

            except subprocess.TimeoutExpired as e:
                LOG.debug(f"Timeout: {tagged_image}")
            
            elapsed = (time.time() - start)
            LOG.debug(f"Whispers {tagged_image} execution took {elapsed/60} minutes")

            if len(whispers.stderr)>0:
                LOG.debug(f"Whispers {tagged_image} error: {whispers.stderr}")
            
            if len(whispers.stdout)>0:
                f = open(f"./{container_name}.log", "w")
                f.write(whispers.stdout)
                f.close

            # Track progress
            with open(completedtagsfile, 'a') as f:        
                f.write(tagged_image + "\n")

                mkdir = subprocess.run(f"rm -rf {tmp_dump}", shell=True, stdout=subprocess.PIPE, text=True, check=True)
                mkdir = subprocess.run(f"rm {tmp_dump}.tar", shell=True, stdout=subprocess.PIPE, text=True, check=True)
                client.images.remove(f"{tagged_image}")

            return

    except Exception as e:
        LOG.debug(f"Error with image: {tagged_image}: {e}", exc_info=True)
        with open("./error-images.txt", 'a') as f:        
            f.write(tagged_image + "\n")
        mkdir = subprocess.run(f"rm -rf {tmp_dump}", shell=True, stdout=subprocess.PIPE, text=True, check=True)
        mkdir = subprocess.run(f"rm {tmp_dump}.tar", shell=True, stdout=subprocess.PIPE, text=True, check=True)
        client.images.remove(f"{tagged_image}")
        exit(0)

def get_image_latest_version(image:str):
    url = f"https://hub.docker.com:443/v2/repositories/{image}/tags/?page_size=25&page=1"
    payload = ""
    headers = {
        "Cookie": "optimizelyEndUserId=oeu1588552838182r0.7987033509302466; _gcl_au=1.1.1697460598.1588552839; _biz_uid=80332eb0e3694249d5118a8282f5858a; _biz_nA=48; _biz_pendingA=%5B%22m%2Fipv%3F_biz_r%3Dhttps%253A%252F%252Fhub.docker.com%252Fr%252Foracle%252Fweblogic-kubernetes-operator%26_biz_h%3D802059049%26_biz_u%3D80332eb0e3694249d5118a8282f5858a%26_biz_s%3D10d4b9%26_biz_l%3Dhttps%253A%252F%252Fhub.docker.com%252Fr%252Foracle%252Fweblogic-kubernetes-operator%252Ftags%26_biz_t%3D1590280334154%26_biz_i%3Doracle%252Fweblogic-kubernetes-operator%2520-%2520Docker%2520Hub%26_biz_n%3D47%26rnd%3D232513%22%5D; ajs_user_id=null; ajs_group_id=null; _ga=GA1.2.1787025428.1588552840; ajs_anonymous_id=%22883ea900-5ad3-4d7d-ab20-8859a44938b4%22; _fbp=fb.1.1588552840330.690238236; _mkto_trk=id:929-FJL-178&token:_mch-docker.com-1588552840335-25829; _biz_flagsA=%7B%22Version%22%3A1%2C%22Mkto%22%3A%221%22%2C%22XDomain%22%3A%221%22%7D; NPS_383366e9_last_seen=1588552845194; dwf_banner=True; _biz_sid=10d4b9; _gid=GA1.2.261156126.1590278909; _gat=1", 
        "Accept": "application/json", 
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:76.0) Gecko/20100101 Firefox/76.0", 
        "Connection": "close", 
        "Host": "hub.docker.com", 
        "Accept-Encoding": "gzip, deflate", 
        "Accept-Language": "en-US,en;q=0.5"
    }
    response = request("GET", url, data=payload, headers=headers)
    response= json.loads(response.text)
    return response.get("results")[0].get("name")