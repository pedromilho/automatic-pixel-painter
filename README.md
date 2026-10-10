# Assistente de Pixels

Aplicativo local para capturar o mapa, detectar os marcadores quadrados de uma camada de referência, conferir uma prévia e pintar um lote de pixels. A interface oferece os modos **Cor por cor** e **Cor específica**.

## Instalação

Requer Windows, Python 3.10 ou mais recente e estes pacotes:

```powershell
python -m pip install opencv-python numpy Pillow pyautogui PyGetWindow
```

## Usar a interface

1. Abra o mapa no Edge, entre no modo de pintura e deixe a paleta visível.
2. Dê dois cliques em `iniciar_bot.cmd`. A interface abre em uma janela separada. Ao fechá-la, o servidor local e o console terminam.
3. Escolha o modo e clique em **Capturar mapa**. Confira a área amarela e os marcadores verdes na prévia.
4. Ajuste a velocidade e o número de pixels do lote. Clique em **Iniciar pintura** e confira o resultado no mapa.

Também é possível iniciar com `python pixel_server.py`. O servidor usa `127.0.0.1` e escolhe uma porta livre.

### Modos de pintura

- **Cor específica:** deixe somente a cor desejada visível na camada de referência e selecione a mesma cor na paleta. O programa clica uma vez em cada marcador, sem usar o color picker.
- **Cor por cor:** deixe as cores desejadas visíveis. Para cada marcador, o programa aciona o color picker, clica para coletar a cor e clica novamente para pintar. A posição do color picker é conferida a cada pixel; se o ícone não for encontrado, o lote é interrompido.

Mantenha `color_picker_modelo.png` e `color_picker_modelo_novo.png` ao lado dos scripts. A janela flutuante da camada de referência é marcada em vermelho na prévia e excluída da pintura.

### Prévia e controles

- Use a roda do mouse para ampliar a prévia. Com zoom, arraste com o botão esquerdo para mover a imagem. Use **Shift + arrastar** para selecionar outra área em qualquer zoom.
- Os sliders **Tamanho X/Y**, abaixo da prévia, ajustam as dimensões da área. **Posição X/Y** deslocam a área sem mudar seu tamanho. O contorno azul mostra o ajuste antes de soltar o slider. Os valores são guardados no navegador e reaplicados nas próximas capturas. **Área automática** limpa o ajuste e restaura o recorte calculado pelo programa.
- O zoom da prévia é apenas visual. A seleção personalizada altera somente a área analisada na captura atual.
- Alterar a área refaz a detecção e reinicia o lote da captura.
- **Pixels neste lote** começa com todos os marcadores restantes. Você pode reduzir o número para testar. Um novo lote continua nos marcadores seguintes; uma nova captura reinicia a sequência.
- **Parar** interrompe antes do próximo pixel. Mover o cursor para o canto superior esquerdo também interrompe pelo mecanismo do PyAutoGUI.
- Se mudar o filtro, o zoom ou a posição do mapa, capture de novo. Mantenha o mapa visível durante a pintura; se ele perder o foco, o programa para.
- O programa não pressiona botões de confirmação nem verifica se a pintura foi aceita. Confira o primeiro pixel antes de aumentar o lote.

## Usar pelo terminal

Para gerar apenas a prévia `preview_pixels.png`, sem pintar:

```powershell
python pixel_detector.py
```

Para pintar um pixel de teste:

```powershell
python pixel_detector.py --paint --limit 1
```

O modo padrão localiza o botão do color picker na paleta. Use `--picker i` para testar o atalho de teclado. Ajuste as pausas com `--speed safe`, `--sample-delay 0.3` ou `--delay 0.1`.

Para escolher uma área sem abrir outra janela, use `--pick-roi` e pressione **F8** em cada canto. Também é possível informar `--roi 180,180,1200,800`. Para analisar uma imagem salva sem clicar:

```powershell
python pixel_detector.py --image "C:\caminho\captura.png" --roi 180,180,1200,950
```

Pressione **Ctrl+C** no terminal ou mova o cursor para o canto superior esquerdo para interromper.

## Janela do mapa

A janela do mapa é encontrada automaticamente pelo título. Deixe a aba do mapa selecionada no navegador antes de capturar. Não é necessário criar um arquivo de configuração. Na linha de comando, é possível informar outro título com `--window-title "trecho do título"`.
