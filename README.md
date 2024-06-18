<!-- PROJECT LOGO -->
<br />
<p align="center">
  <!-- <a href="https://github.com/agentsea/skillpacks">
    <img src="https://project-logo.png" alt="Logo" width="80">
  </a> -->

  <h1 align="center">SurfPizza</h1>
    <p align="center">
    <img src="https://storage.googleapis.com/guisurfer-assets/SurfPizza.webp" alt="SurfPizza Logo" width="200" style="border-radius: 20px;">
    </p>
  <p align="center">
    A GUI surfer which slices up the screen
    <br />
    <a href="https://docs.hub.agentsea.ai/introduction"><strong>Explore the docs »</strong></a>
    <br />
    <br />
    <a href="https://github.com/agentsea/surfpizza">View Demo</a>
    ·
    <a href="https://github.com/agentsea/surfpizza/issues">Report Bug</a>
    ·
    <a href="https://github.com/agentsea/surfpizza/issues">Request Feature</a>
  </p>
  <br>
</p>

## Install

```sh
pip install surfkit
```

## Quick Start

Create a tracker

```sh
surfkit create tracker
```

Create a device

```sh
surfkit create device --provider gce --name device01
```

Create the agent

```sh
surfkit create agent -t pbarker/SurfPizza --name agent01
```

Solve a task

```sh
surfkit solve "Search for common varieties of french ducks" \
  --device device01 \
  --agent agent01
```

## Documentation

See our [docs](https://docs.hub.agentsea.ai) for more information on how to use SurfPizza.

## Developing

Install dependencies

```sh
poetry install
```

Create a tracker

```sh
surfkit create tracker
```

Create a device

```sh
surfkit create device --provider gce --name george
```

Solve a task

```sh
surfkit solve "Search for common varieties of french ducks" \
--device george --agent-file ./agent.yaml --runtime process
```

## Community

Come join us on [Discord](https://discord.gg/hhaq7XYPS6).

