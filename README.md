# NFL Imperialism

A custom-built territory conquest simulator inspired by the viral "Madden Imperialism" videos on YouTube.

The kiddos had Gemini build this to bring the videos to life. Instead of coloring in maps by hand after every game, this engine handles the geography, battle logic, and map updates automatically, letting them focus on the fun of the tournament.

## Features

* **Automated Mapping:** Instantly assigns every US county to the nearest team using Voronoi diagrams.
* **Battle Wheel:** A two-stage spinner (Attacker -> Defender) to build anticipation for the kids.
* **History Replay:** Watch the entire conquest unfold from Day 1 to the current state with a cinematic replay mode.
* **Resilient Saves:** Auto-saves progress to prevent tears if the browser is accidentally refreshed.

## Credits & Development
Intended to be entirely built by AI with collaboration from kiddos that don't know how to code. But required some human intervention when Gemini got confused and kept breaking functionality while attempting to add new features and fix bugs.

* **Lead Architect:** Gemini (Google DeepMind) - Wrote the Python/Streamlit code and geospatial logic based on prompts from the kiddos.
* **Engineering Lead & Debugging:** User - Provided architectural direction, fixed critical state management bugs, and resolved versioning conflicts when the AI hallucinated or broke the build.

## Prerequisites

### Docker Setup

To run this application, you need:

1. **Docker** (version 20.10 or later)
2. **Docker Compose** (version 2.0 or later)

Install Docker on your system:
- **Ubuntu/Debian**: `sudo apt-get install docker.io docker-compose`
- **macOS**: Download from [Docker Desktop](https://www.docker.com/products/docker-desktop)
- **Windows**: Download from [Docker Desktop](https://www.docker.com/products/docker-desktop)

## Quick Start

### Using Docker Compose (Recommended)

1. **Clone or download** the project files
2. **Navigate** to the project directory:
   ```bash
   cd imperialism
   ```
3. **Launch the application**:
   ```bash
   docker compose up --build
   ```
4. **Access the app** in your web browser at:
   ```
   http://localhost:8501
   ```

The application will be available on all network interfaces (0.0.0.0:8501), making it accessible from other devices on your network.
* *e.g. To play from an iPad on the same network:* Find your computer's local IP (e.g., `192.168.1.x`) and visit `http://192.168.1.x:8501`.

### Docker Compose Commands

- **Start the app**: `docker compose up --build`
- **Stop the app**: `docker compose down`
- **View logs**: `docker compose logs -f`
- **Rebuild after changes**: `docker compose up --build`

## Application Usage

1. **Start a New Game**: Configure the number of counties and players
2. **Watch Battles**: Automated battles run between territories
3. **Manage Counties**: Reassign conquered territories to players
4. **Save Progress**: Game state is automatically saved

## Development

### Local Development

If you prefer to run locally without Docker:

1. **Install Conda** (Miniconda or Anaconda)
2. **Create environment**:
   ```bash
   conda env create -f environment.yml
   conda activate imperialism
   ```
3. **Run the app**:
   ```bash
   streamlit run streamlit_app.py
   ```

## License

**MIT License**

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files, to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software.
