# azure-pipeline-generator
This is a YAML Pipeline generator for Azure DevOps. This was designed with Azure DevOps did not have a YAML pipeline definition. It is now advised to use the Microsoft supported layer. 


## Execute Hello World
1. install dependencies `pip3 install -r requirements.txt`
1. adjust globalVars file to match your project
2. adjust phase template to match your projects queue ids (for agents)
3. `python3 ./pipelineGenerator.py ./helloworld.yml  -d` 
