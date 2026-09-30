from openai import OpenAI;

print(OpenAI().chat.completions.create(model='gpt-4o-mini', messages=[{'role':'user','content':'say ok'}]).choices[0].message.content)