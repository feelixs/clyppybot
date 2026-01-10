# Use Python 3.12.6 as a parent image
FROM python:3.12.6-slim

LABEL version="1.0"
LABEL description="This is a custom Python image for my application."
COPY . .

RUN apt-get -yq update && apt-get install -y git
RUN pip3 install -r requirements.txt
RUN apt-get install -yq ffmpeg

RUN chmod +x run.sh

CMD ["./run.sh"]
