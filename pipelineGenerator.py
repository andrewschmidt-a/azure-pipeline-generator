"""
Usage format: 
python[.exe] .\pipelineGenerator.py ..\Pipelines\pipeline.yml .\{{deployment}}.yml -d -n "Deploy: {{ApplicationAcronym}}-{{DeplyEnvironment}}
Usage Examples: 
python .\pipelineGenerator.py ..\Pipelines\pipeline.yml .\bbdemo.yml   # just create the pipeline
python .\pipelineGenerator.py ..\Pipelines\pipeline.yml .\bbdemo.yml -d # create the pipeline and trigger a deploy
python .\pipelineGenerator.py ..\Pipelines\pipeline.yml .\bbdemo.yml -d -n "Deploy: scott-test" -token "Omcycm9penZyeWszeG1rYnc0bzV4d2UyeWJwaHRqNWpiY2xwZzZ5cGx3aHF1bWo1bms2cHE="# create a named pipeline and trigger a deploy
python .\pipelineGenerator.py ..\Pipelines\pipeline.1.yml .\scottdev.yml -n "Deploy: scott-test"
overide the default package version with the -v flag
python ./pipelineGenerator.py ../Pipelines/pipeline.yml ./bbdemo.1.yml -n "Deploy: scott-test" -v UniversalPackageVersion 3.1.1903181517 -token "Omcycm9penZyeWszeG1rYnc0bzV4d2UyeWJwaHRqNWpiY2xwZzZ5cGx3aHF1bWo1bms2cHE="
provide PAT token as an additional argument -t "Omcycm9penZyeWszeG1rYnc0bzV4d2UyeWJwaHRqNWpiY2xwZzZ5cGx3aHF1bWo1bms2cHE="

"""
import click

@click.command()
@click.argument('inputFile')
@click.argument('variablefiles', nargs=-1)
@click.option('--deploy', '-d', is_flag=True, help='Trigger the pipeline when updated')
@click.option('--name', '-n', is_flag=False, help='Name of the Pipeline')
@click.option('--variables', '-v', nargs=2, multiple=True, is_flag=False, help='Variable in format {VariableName} {VariableValue}')
@click.option('--token','-token',is_flag=False, help='Base64 encoded PAT token')
def main(inputfile, variablefiles, deploy, name, variables, token):
    
    #print(opts)
    pg = PipelineGenerator()
    pg.__init__(directory='', token=token)

    if(len(variablefiles)):
        pg.loadVariableFiles =  variablefiles
        
        with open(variablefiles[-1], 'r') as stream:
            try:
                vars = yaml.load(stream)
                pg.globalVars.update(dict(map(lambda x: ('_'+x, vars[x]), vars)))
            except yaml.YAMLError as exc:
                print(exc)
    pg.loadReleaseDef(inputfile)
    if name:
        pg.releaseDef['name'] = name
    if variables:
        for var in variables:
            pg.releaseDef['variables'][var[0]] = {"value":var[1]}
    pg.updateRelease()
    if deploy:
        pg.triggerRelease()

import json, yaml
import uuid

import requests
import urllib
from jinja2 import Template, FileSystemLoader, Environment
from colorama import Fore, Back, Style 
class PipelineGenerator:
    
    def __init__(self, directory='', token=''):
        self.__pipelineId =''
        self.__authorization = 'Basic {}'.format(token)
        
        self.directory = directory
        self.templateLoader = FileSystemLoader(searchpath=self.directory+"Templates")
        self.templateEnv = Environment(loader=self.templateLoader)

        with open(self.directory+'globalVars.json', 'r') as globalsFile:
            self.globalVars = json.load(globalsFile)

        self.artifactTemplates = dict()
        self.phaseTemplate = self.templateEnv.get_template("phase.j2")
        self.stageTemplate = self.templateEnv.get_template("stage.j2")
        self.triggerTemplate = self.templateEnv.get_template("trigger.j2")
        self.urlRootVsrm = "https://vsrm.dev.azure.com/"+self.globalVars['_orgName']+"/"+self.globalVars['_projectName']
        self.urlRoot = "https://dev.azure.com/"+self.globalVars['_orgName']+"/"+self.globalVars['_projectName']
        self.loadVariableFiles = list()
    

    ##PUBLIC
    def loadReleaseDef(self, file):
        self.releaseDef = dict()
        with open(file, 'r') as stream:
            try:
                self.releaseDef = yaml.load(stream)
            except yaml.YAMLError as exc:
                print(Fore.RED + "YAML is invalid"+Style.RESET_ALL)
                print(exc)
        self.convertReleaseDef()
    def getVariablesFromFile(self, file):
        with open(self.directory+file, 'r') as stream:
                try:
                    self.releaseDef['variables'].update(yaml.load(stream))
                except yaml.YAMLError as exc:
                    print(exc)
    def convertReleaseDef(self):
        ## Variables
        
        if isinstance(self.releaseDef['variables'], str):
            self.releaseDef['variables'] = dict()
            self.getVariablesFromFile(self.releaseDef['variables'])
        if isinstance(self.releaseDef['variables'], list):
            files = self.releaseDef['variables']
            self.releaseDef['variables'] = dict()
            for file in files:
                self.getVariablesFromFile(file)
        if "variableOverride" in self.releaseDef:
            print(self.releaseDef['variableOverride'])
            self.releaseDef['variables'].update(self.releaseDef['variableOverride'])
        for file in self.loadVariableFiles:
            self.getVariablesFromFile(file)
        #print(list(enumerate(self.releaseDef['variables'])))
        self.releaseDef['variables'] = dict(map(lambda x: (x,{"value":self.releaseDef['variables'][x]}), self.releaseDef['variables']))
        # with open('test.json', 'w') as outfile:
        #     json.dump(self.releaseDef['variables'], outfile)
        
        print("Imported", len(self.releaseDef['variables']), "variables")

        #print(self.releaseDef['variables'], "\n\n")
        
        ## Universal Tasks
        if 'universalTasks' in self.releaseDef:
            self.universalTasks = list(map(self.__mapTasks,enumerate(self.releaseDef['universalTasks'])))
        else:
            self.universalTasks = []
            
        print("Imported", len(self.universalTasks), "Universal Tasks")

        ## Universal End Tasks 
        if 'universalLastTasks' in self.releaseDef:
            self.universalLastTasks = list(map(self.__mapTasks,enumerate(self.releaseDef['universalLastTasks'])))
        else:
            self.universalLastTasks = []    
            
        print("Imported", len(self.universalLastTasks), "Universal Last Tasks")
       
        
        ## Artifacts
        if 'artifacts' in self.releaseDef:
            self.releaseDef['artifacts'] = list(map(self.__mapArtifacts,self.releaseDef['artifacts']))
        else:
            self.releaseDef['artifacts'] = []
        print("Imported", len(self.releaseDef['artifacts']), "artifact definitions")
        ## Stages
        self.releaseDef['stages'] = list(map(self.__mapStages,enumerate(self.releaseDef['stages'])))
        print("Imported", len(self.releaseDef['stages']), "stages")


        
        ## Triggers
        if 'triggers' in self.releaseDef:
            self.releaseDef['triggers'] = list(map(self.__mapTriggers,self.releaseDef['triggers']))
        else:
            self.releaseDef['triggers'] = []
        print("Imported", len(self.releaseDef['triggers']), "triggers")


    def updateRelease(self):
        attempts = 5
        self.__getOrCreatePipeline(self.releaseDef['name'])
        for i in range(attempts): # attempt to do this x times
            url = self.urlRootVsrm + '/_apis/release/definitions/'+str(self.__pipelineId)+'?api-version=5.0'
            #print(url)
            response = requests.get(url, headers={
                'Authorization': self.__authorization
            })
            pipelinedata = json.loads(response.text)
            #print(pipelinedata['revision'])
            print("Get most recent definition:",response.status_code)


            url = self.urlRootVsrm + '/_apis/Release/definitions?api-version=5.0'
            data = dict({	
                "id": self.__pipelineId,
                "revision": pipelinedata['revision'],
                "environments":self.releaseDef['stages'],
                "artifacts":self.releaseDef['artifacts'],
                "variables":self.releaseDef['variables'],
                "triggers": self.releaseDef['triggers'],
                "name":self.releaseDef['name']
            })

            response = requests.put(url, data=json.dumps(data), headers={
                'Authorization': self.__authorization, 
                'Content-Type':'application/json', 
                'accept': 'application/json;api-version=5.0;excludeUrls=true'
            })
            print("Put new release definition:",response.status_code)
            if response.status_code == 200:
                break #yea!!!

        if response.status_code != 200:
            print("\n Response:\n" + str(response.json()) + "\n")

        print(response.json()['_links']['web']['href'])
        return response

    def triggerRelease(self):
        url = self.urlRootVsrm + '/_apis/release/releases?api-version=5.0'
        data = dict({	
            "definitionId": self.__pipelineId
        })

        response = requests.post(url, data=json.dumps(data), headers={
            'Authorization': self.__authorization, 
            'Content-Type':'application/json'
        })
        print("Trigger new release:",response.status_code)
        if response.status_code != 200:
            print(response.json())
        return response
     
    
    ## PRIVATE
    def __getOrCreatePipeline(self, name):
        url = self.urlRootVsrm + '/_apis/release/definitions?api-version=5.0&isExactNameMatch=true&searchText='+urllib.parse.quote(name)
        #print(url)
        response = requests.get(url, headers={
            'Authorization': self.__authorization
        })
        if response.status_code == 200:
            data = response.json()
            if data['count'] == 0:
                self.__pipelineId = self.__createPipeline(name)
                return self.__pipelineId
            else:
                self.__pipelineId = str(data['value'][0]['id'])
                #print("Andrew TEst: ", self.__pipelineId)
                return str(data['value'][0]['id'])
        else:
            raise Exception(response.text)
    def __createPipeline(self, name):
        with open(self.directory+"Templates/dummyStage.yml", 'r') as stream:
            try:
                dummy_stage = yaml.load(stream)
            except yaml.YAMLError as exc:
                print(exc)
        data = dict({
            "id":0,
            "name":name,
            "environments": list(map(self.__mapStages,enumerate(dummy_stage['stages'])))
        })
        url = self.urlRootVsrm + '/_apis/release/definitions?api-version=5.0&excludeUrls=true'
        
        response = requests.post(url,data=json.dumps(data), headers={
            'Authorization': self.__authorization, 
            'Content-Type':'application/json'
        })
        #print(response.status_code)
        if response.status_code == 200:
            data = response.json()
            #print("Andrew TEst: ", data['id'])
            return data['id']
        else:
            raise Exception(response.text)
    def __mapArtifacts(self,artifact):
        #print(artifact)
        if artifact['type'] not in self.artifactTemplates: #cache templates
            self.artifactTemplates[artifact['type']] = self.templateEnv.get_template("artifacts/"+artifact['type']+".j2")

        if artifact['type'] == "git" and "id" not in artifact:
            url = self.urlRoot + '/_apis/git/repositories/'+urllib.parse.quote(artifact['name'])+'?5.1-preview.3'
            
            response = requests.get(url, headers={
                'Authorization': self.__authorization, 
                'Content-Type':'application/json'
            })
            if response.status_code == 404:
                raise(response.json()['message'])
            artifact['id'] = response.json()['id']
        if artifact['type'] == "build" and "version" in artifact and "buildId" not in artifact:
            url = self.urlRoot + '/_apis/build/builds?5.1-preview.3&buildNumber='+urllib.parse.quote(artifact['version'])
            
            response = requests.get(url, headers={
                'Authorization': self.__authorization, 
                'Content-Type':'application/json'
            })
            if response.status_code == 404:
                raise(response.json()['message'])
            
            if response.json()['count'] == 0:
                raise("No build found matching version: "+ artifact['version'])
            
            artifact['buildId'] = response.json()["value"][0]['id']
        
        #print(artifact)
        artifact.update(self.globalVars)
        print(json.loads(self.artifactTemplates[artifact['type']].render(artifact)))
        return json.loads(self.artifactTemplates[artifact['type']].render(artifact))
    def __mapTriggers(self,trigger):
        #print(artifact)
        trigger.update(self.globalVars)
        return json.loads(self.triggerTemplate.render(trigger))

    def __mapTasks(self,task):
        i = task[0]
        task = task[1]
        task.update(self.globalVars)
        task.update({"_taskGuid": str(uuid.uuid4())})
        template = self.templateEnv.get_template("tasks/"+task['type']+".j2")

        print("\n\n\n\n", template.render(task), "\n\n\n\n")
        task =json.loads(template.render(task))
        
        return task
        
    def __mapPhases(self,phase):
        i = phase[0]
        phase = phase[1]
        phase.update({"_rank":i+1})
        phase.update(self.globalVars)
        tasks = list(map(self.__mapTasks, enumerate(phase.pop("tasks"))))
        tasks = self.universalTasks + tasks  + self.universalLastTasks
        print(self.phaseTemplate.render(phase))
        phase = json.loads(self.phaseTemplate.render(phase))
        phase.update({"workflowTasks":tasks})
        return phase

    def __mapStages(self,stage):
        i = stage[0]
        stage = stage[1]
        stage.update(self.globalVars)
        stage.update({"_rank":i+1})
        phases = list(map(self.__mapPhases, enumerate(stage.pop("phases"))))
        stage = json.loads(self.stageTemplate.render(stage))
        stage.update({"deployPhases":phases})
        return stage

if __name__ == "__main__":
   main()
