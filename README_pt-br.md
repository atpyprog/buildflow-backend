# 🏗️ BuildFlow — Sistema de Gestão de Obras

## 👋 Apresentação Pessoal

Este é o meu primeiro projeto com foco profissional, criado para aplicar conceitos reais de backend, banco de dados e integração com APIs externas.

O BuildFlow nasceu de uma inspiração pessoal.
O meu avô paterno era engenheiro civil e, quando eu era criança, costumava me levar para visitar algumas das obras em que trabalhava.
Eu me divertia com os seus colaboradores e eles me mostravam um pouco de suas atividades. 
Sempre achei importante o planejamento e a execução harmónica, e o meu avô sempre falou que planejamento é a essencia de uma boa construção civil — e como cada detalhe fazia diferença no resultado final.

Essa lembrança me motivou a criar um sistema que pudesse ajudar outros profissionais da construção civil, pessoas como o meu avô, a terem um planejamento mais eficiente, uma visão mais organizada do progresso e uma gestão inteligente dos riscos climáticos que podem afetar uma obra.

---

## 🚀 Objetivo do Projeto

O **BuildFlow** é um sistema de **gestão e acompanhamento de obras**, desenvolvido com **Python + FastAPI** e **PostgreSQL**, com o objetivo de oferecer uma base sólida para:

- 📋 Cadastrar **projetos**, **lotes** e **setores** da obra;  
- 🧱 Registrar o **progresso diário** das atividades;  
- 🌦️ Integrar **previsões meteorológicas** via **API Open-Meteo**;  
- 🚨 Gerar **alertas automáticos de risco climático**;  
- 🪪 Registrar **issues (problemas e ocorrências)** com histórico e status.  

---

## 🧠 Conceito Educacional

O projeto foi desenvolvido como uma **ponte entre teoria e prática**, com o propósito de consolidar conhecimentos em:

- Programação Orientada a Objetos (POO) em Python;
- Modelagem e integração com banco de dados PostgreSQL;  
- ORM assíncrono com **SQLAlchemy 2.0 + asyncpg**;  
- Criação de **APIs RESTful** com **FastAPI**;  
- Boas práticas de estruturação de projeto backend;  
- Integração com **serviços externos (APIs públicas)**;  
- Manipulação de dados meteorológicos e automação de alertas.  

---

## ⚙️ Tecnologias Principais

| Camada | Tecnologia |
|--------|-------------|
| Linguagem | Python 3.11 |
| Framework Web | FastAPI |
| Banco de Dados | PostgreSQL |
| ORM | SQLAlchemy 2.0 (assíncrono) |
| API Externa | Open-Meteo |
| Ferramentas | PyCharm, PgAdmin |
| Dependências | `requirements.txt` |
| Testes e Docs | Swagger UI, HTTPie |

---

## 🧩 Estrutura do Projeto
```bash
buildflow/
├─ app/
│  ├─ __init__.py
│  ├─ main.py
│  ├─ api/
│  │  └─ v1/
│  │     ├─ router.py
│  │     ├─ projects.py
│  │     ├─ lots.py
│  │     ├─ issues.py
│  │     ├─ progress.py
│  │     └─ weather.py
│  ├─ clients/
│  │  └─ open_meteo.py
│  ├─ core/
│  │  └─ config.py
│  ├─ db/
│  │  └─ session.py
│  ├─ services/
│  │  ├─ rules_engine.py
│  │  ├─ apply_rules.py
│  │  ├─ weather_capture.py
│  │  └─ weather_normalize.py
│  └─ utils/
│     ├─ open_meteo.py
│     ├─ open_meteo_week.py
│     └─ weather_codes.py
├─ uploads/
├─ .env.example
├─ requirements.txt
└─ README.md
```

---

## 💻 Como Rodar Localmente:

1️⃣ Clonar o repositório
    git clone https://github.com/<seu-usuario>/buildflow.git
    cd buildflow

2️⃣ Criar e ativar um ambiente virtual
    
    python -m venv venv
    # Windows
    venv\Scripts\activate
    # macOS/Linux
    source venv/bin/activate

3️⃣ Instalar as dependências

    pip install -r requirements.txt

4️⃣ Configurar variáveis de ambiente

    Copie o arquivo .env.example e renomeie para .env.
    Preencha com as credenciais corretas do banco PostgreSQL e da API Open-Meteo:
    
    DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/buildflow
    OPEN_METEO_API_URL=https://api.open-meteo.com/v1/forecast

5️⃣ Executar o servidor FastAPI

    uvicorn app.main:app --reload

    Acesse a documentação interativa:
    
    Swagger UI → http://127.0.0.1:8000/docs
    
    Redoc → http://127.0.0.1:8000/redoc

---

## 🧭 Organização do Projeto por Features

O **BuildFlow** segue uma organização por features e responsabilidades, em vez da estrutura tradicional models/ e schemas/.
```
 Diretório	        Função
 - app/api/	        → Define os endpoints REST (FastAPI) divididos por área funcional (projects, issues, weather, etc.)
 - app/clients/	        → Integrações externas — como o cliente da API Open-Meteo
 - app/core/	        → Configurações centrais e variáveis de ambiente
 - app/db/	        → Sessão e engine do banco de dados PostgreSQL
 - app/services/	→ Contém a lógica de domínio: captura, normalização e análise de dados climáticos, motor de regras, etc.
 - app/utils/	        → Funções auxiliares e constantes reutilizáveis (ex.: códigos de clima, formatação de dados)
```
---

## 🌦️ Integração com Open-Meteo

O módulo meteorológico permite consultar e armazenar previsões horárias e diárias de:
```
 🌡️ Temperatura

 🌧️ Probabilidade de chuva

 💨 Velocidade do vento
```
Esses dados são processados e salvos nas tabelas weather_batch e weather_snapshot, servindo como base para gerar issues preventivas automáticas — alertas que indicam condições adversas (chuva, vento forte, etc.) que podem afetar as tarefas planejadas da obra.

---

## 🧪 Próximos Passos

 -  🔗 Integração com API Open-Meteo ✅ 
 -  📥 Normalização e persistência dos dados meteorológicos ✅
 -  🌩️ Criação das regras de risco climático
 -  📊 Implementação dos relatórios semanais de progresso
 -  🖼️ Upload real de imagens e anotações de campo
 -  🌐 Interface web simples para visualização de dados

---

## 💡 Sobre o uso de Inteligência Artificial

O BuildFlow também representa um aprendizado sobre como a tecnologia pode trabalhar tão bem com a necessidade e ideias de nós seres humanos.
Durante o desenvolvimento, ferramentas de Inteligência Artificial foram utilizadas como apoio para revisão de ideias, documentação e boas práticas de código.
Todas as decisões técnicas e implementações foram realizadas com análise e compreensão humanas, utilizando a IA apenas como um suporte educacional e ferramenta de aprimoramento.

---

## ✍️ Autor

Alexandre Tavares

📍 Porto, Portugal

💻 Estudante e desenvolvedor Python em formação

📚 Em constante aprendizado sobre backend, banco de dados e integração de APIs
```
“Aprender é construir. E o BuildFlow é parte dessa construção.”
```

---
### 🪪 Licença
Este projeto é licenciado sob a **Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)**.  
Uso comercial não autorizado é proibido.