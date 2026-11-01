# Deploy no Render

O repositório define um serviço Docker em `render.yaml`. O GitHub Actions solicita um deploy no Render somente depois que o workflow **CI** termina com sucesso em um `push` para `main`; o Render compila e publica o commit mais recente. Deploy automático por push direto do Render fica desativado para manter o CI como gate.

## Configuração inicial

1. No Render, crie um Blueprint e conecte `Pedrodek/myself`, usando o `render.yaml` da branch `main`. Isso cria o serviço web `myself` com o Dockerfile do repositório, health check em `/healthz` e uma `HUB_SECRET_KEY` gerada pelo Render.
2. No serviço criado, abra **Settings** e copie o **Deploy Hook**.
3. No GitHub, abra **Settings → Secrets and variables → Actions** e crie o secret `RENDER_DEPLOY_HOOK` com o URL do hook. Não coloque esse URL no código.
4. Acompanhe a execução de **Deploy to Render** na aba **Actions** e o status final na aba **Events** do serviço no Render.

O serviço libera `HUB_ALLOW_SAMPLE_CONTENT=true`, conforme autorizado, então o site ficará no ar com o currículo fictício atual. Atualize os arquivos em `content/` e remova `sample: true` nos dois idiomas antes de usar como currículo real; depois disso, retire essa variável do Blueprint para voltar à proteção de produção.

O Render fornece `RENDER_EXTERNAL_URL`; a aplicação a usa como URL canônica padrão quando `HUB_SITE_URL` não foi definida. Para domínio próprio, configure `HUB_SITE_URL` com a URL HTTPS pública.

O plano gratuito do Render pode suspender o serviço após inatividade. A solicitação do deploy via hook não espera a conclusão do build; confirme o status no Render antes de considerar a nova versão publicada.
