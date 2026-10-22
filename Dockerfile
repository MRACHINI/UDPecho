FROM python:3.12-alpine

WORKDIR /app
COPY udpecho.py .

# run as an unprivileged user (port 27015 > 1024, no root needed)
RUN adduser -D -H echo
USER echo

ENV UDPECHO_PORT=27015 \
    UDPECHO_MAGIC="NESTPROBE1|" \
    UDPECHO_MAXLEN=512 \
    UDPECHO_LOGSEC=600

EXPOSE 27015/udp
CMD ["python", "-u", "/app/udpecho.py"]
