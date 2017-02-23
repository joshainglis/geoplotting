FROM continuumio/miniconda3

COPY environment.yml /analysis/environment.yml
WORKDIR /analysis

RUN conda env create
RUN echo "source activate geoplotting" >> /root/.bashrc