# Use Miniconda base image for conda support
FROM continuumio/miniconda3

WORKDIR /app

# Copy and create conda environment from environment.yml
COPY environment.yml .
RUN conda env create -f environment.yml && \
    conda clean -afy

# Copy the Streamlit app
COPY streamlit_app.py .
COPY inputs/ ./inputs/
COPY saved/ ./saved/

# Expose port 8501 (default Streamlit port)
EXPOSE 8501

# Command to run Streamlit on 0.0.0.0 with conda environment
CMD ["conda", "run", "-n", "imperialism", "streamlit", "run", "streamlit_app.py", "--server.address=0.0.0.0", "--server.port=8501"]
