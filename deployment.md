saisakthidar@cloudshell:~ (project-8d4e3e27-b826-4e07-929)$ gcloud compute instances create breakthrough-app \
    --zone=us-central1-a \
    --machine-type=e2-standard-4 \
    --boot-disk-size=50GB \
    --boot-disk-type=pd-standard \
    --image-family=ubuntu-2204-lts \
    --image-project=ubuntu-os-cloud \
    --tags=http-server,https-server
WARNING: You have selected a disk size of under [200GB]. This may result in poor I/O performance. For more information, see: https://developers.google.com/compute/docs/disks#performance.

Created [https://www.googleapis.com/compute/v1/projects/project-8d4e3e27-b826-4e07-929/zones/us-central1-a/instances/breakthrough-app].
WARNING: Some requests generated warnings:
 - Disk size: '50 GB' is larger than image size: '10 GB'. You might need to resize the root repartition manually if the operating system does not support automatic resizing. See https://cloud.google.com/compute/docs/disks/add-persistent-disk#resize_pd for details.

NAME: breakthrough-app
ZONE: us-central1-a
MACHINE_TYPE: e2-standard-4
PREEMPTIBLE: 
INTERNAL_IP: 10.128.0.4
EXTERNAL_IP: 34.60.83.58