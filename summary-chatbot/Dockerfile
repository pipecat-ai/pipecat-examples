FROM python:3.10-bullseye

RUN mkdir /app
RUN mkdir /app/recordings
RUN mkdir /app/summaries
COPY *.py /app/
COPY requirements.txt /app/

WORKDIR /app
RUN pip3 install -r requirements.txt

EXPOSE 7860

CMD ["python3", "server.py"]
