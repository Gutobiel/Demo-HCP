import requests

url = "https://www.hcpneus.com.br/pesquisa?t=16"
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36',
}

print(f"Buscando {url}...\n")
response = requests.get(url, headers=headers)

print(f"Status retornado: {response.status_code}")
print("--- CONTEÚDO DA PÁGINA (RESPOSTA DO SERVIDOR) ---\n")

# Vamos limitar a 2000 caracteres pra não estourar a tela se for longo, mas pegar o miolo
print(response.text[:2000])

# Vamos tentar procurar por assinaturas comuns de captcha no HTML retornado
texto_lower = response.text.lower()
if 'cloudflare' in texto_lower or 'cf-browser-verification' in texto_lower:
    print("\n--- DIAGNÓSTICO: BLOQUEIO DO CLOUDFLARE DETECTADO ---")
elif 'recaptcha' in texto_lower:
    print("\n--- DIAGNÓSTICO: GOOGLE RECAPTCHA DETECTADO ---")
elif 'akamai' in texto_lower:
    print("\n--- DIAGNÓSTICO: AKAMAI BOT MANAGER DETECTADO ---")
elif 'incapsula' in texto_lower or 'imperva' in texto_lower:
    print("\n--- DIAGNÓSTICO: IMPERVA/INCAPSULA DETECTADO ---")
elif 'datadome' in texto_lower:
    print("\n--- DIAGNÓSTICO: DATADOME DETECTADO ---")
elif 'maintenance' in texto_lower or 'manutenção' in texto_lower:
    print("\n--- DIAGNÓSTICO: PÁGINA DE MANUTENÇÃO DO MAGENTO DETECTADA ---")
else:
    print("\n--- DIAGNÓSTICO: TIPO DE BLOQUEIO DESCONHECIDO ---")
    
# Salvar em um arquivo HTML na raiz pra você poder abrir no seu navegador e ver com seus próprios olhos.
with open("pagina_bloqueada_teste.html", "w", encoding='utf-8') as f:
    f.write(response.text)
print("\nSalvo também no arquivo 'pagina_bloqueada_teste.html' na pasta do projeto.")
