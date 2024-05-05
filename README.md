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
    A GUI surfer which uses coordinate dots for grounding
    <br />
    <a href="https://github.com/agentsea/surfpizza"><strong>Explore the docs »</strong></a>
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

## Usage

Create an agent

```sh
surfkit create agent -f ./agent.yaml --runtime { process | docker | kube } --name foo
```

List running agents

```sh
surfkit list agents --runtime process
```

Use the agent to solve a task

```sh
surfkit solve --agent foo --description "Search for french ducks" --device-type desktop -r process
```

Get the agent logs

```sh
surfkit logs --agent foo -r process
```

Delete the agent

```sh
surfkit delete --agent foo -r process
```
