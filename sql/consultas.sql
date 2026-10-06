-- Consultas do estudo. Cada bloco começa com "-- nome: <identificador>" e é
-- executado por scripts/03_analisar.py sobre as tabelas:
--   coletas_rs        preço por revenda e data no RS (ANP)
--   preco_mensal_uf   preço médio mensal por UF e Brasil (ANP)
--   composicao        composição do preço do P13 por local e mês (ANP/Sindigás)
--   vendas_p13_rs     vendas mensais de P13 com destino ao RS, em mil toneladas (ANP/Sindigás)
--   ipca              número-índice mensal do IPCA (IBGE)
-- O parâmetro :inicio_12m é o primeiro mês da janela dos últimos 12 meses com dados.

-- nome: preco_anual
-- Preço médio anual ao consumidor, RS e Brasil, ponderado pelo número de coletas.
SELECT substr(mes, 1, 4) AS ano,
       ROUND(SUM(CASE WHEN uf = 'RS' THEN preco_medio * coletas END) / SUM(CASE WHEN uf = 'RS' THEN coletas END), 2) AS rs,
       ROUND(SUM(CASE WHEN uf = 'BR' THEN preco_medio * coletas END) / SUM(CASE WHEN uf = 'BR' THEN coletas END), 2) AS brasil
FROM preco_mensal_uf
WHERE uf IN ('RS', 'BR')
GROUP BY ano
ORDER BY ano;

-- nome: preco_mensal
-- Série mensal do preço médio, RS e Brasil.
SELECT mes,
       MAX(CASE WHEN uf = 'RS' THEN preco_medio END) AS rs,
       MAX(CASE WHEN uf = 'BR' THEN preco_medio END) AS brasil,
       MAX(CASE WHEN uf = 'RS' THEN coletas END) AS coletas_rs
FROM preco_mensal_uf
WHERE uf IN ('RS', 'BR')
GROUP BY mes
ORDER BY mes;

-- nome: ranking_uf
-- Preço médio por UF nos últimos 12 meses.
SELECT uf, ROUND(SUM(preco_medio * coletas) / SUM(coletas), 2) AS preco, SUM(coletas) AS coletas
FROM preco_mensal_uf
WHERE uf <> 'BR' AND mes >= :inicio_12m
GROUP BY uf
ORDER BY preco;

-- nome: composicao_rs
-- Parcelas do preço no RS, mês a mês. Produtor inclui os tributos federais.
SELECT mes,
       MAX(CASE WHEN componente = 'produtor_com_tributos_federais' THEN valor END) AS produtor,
       MAX(CASE WHEN componente = 'icms' THEN valor END) AS icms,
       MAX(CASE WHEN componente = 'margem_distribuicao' THEN valor END) AS distribuicao,
       MAX(CASE WHEN componente = 'margem_revenda' THEN valor END) AS revenda,
       MAX(CASE WHEN componente = 'preco_consumidor' THEN valor END) AS consumidor
FROM composicao
WHERE local = 'Rio Grande do Sul'
GROUP BY mes
ORDER BY mes;

-- nome: margem_revenda_uf
-- Margem bruta de revenda por UF no último mês disponível.
SELECT local, valor AS margem_revenda
FROM composicao
WHERE componente = 'margem_revenda'
  AND local <> 'Brasil'
  AND mes = (SELECT MAX(mes) FROM composicao WHERE componente = 'margem_revenda' AND valor IS NOT NULL)
ORDER BY valor;

-- nome: municipios_12m
-- Preço por município gaúcho nos últimos 12 meses.
SELECT municipio,
       COUNT(*) AS coletas,
       COUNT(DISTINCT cnpj) AS revendas,
       ROUND(AVG(preco_venda), 2) AS preco_medio,
       MIN(preco_venda) AS minimo,
       MAX(preco_venda) AS maximo
FROM coletas_rs
WHERE mes >= :inicio_12m
GROUP BY municipio
HAVING COUNT(*) >= 50
ORDER BY preco_medio;

-- nome: municipios_anual
-- Preço médio anual por município, para acompanhar a posição de cada cidade.
SELECT substr(mes, 1, 4) AS ano, municipio, ROUND(AVG(preco_venda), 2) AS preco_medio, COUNT(*) AS coletas
FROM coletas_rs
GROUP BY ano, municipio
HAVING COUNT(*) >= 30
ORDER BY ano, municipio;

-- nome: bandeira_anual
-- Diferença entre o preço de cada coleta e a média do mesmo município no mesmo mês,
-- por tipo de bandeira. Compara revendas que disputam o mesmo mercado.
-- 2018 fica de fora: nos arquivos daquele ano toda revenda aparece como BRANCA.
WITH base AS (
    SELECT substr(mes, 1, 4) AS ano, tipo_bandeira,
           preco_venda - AVG(preco_venda) OVER (PARTITION BY municipio, mes) AS desvio
    FROM coletas_rs
    WHERE mes >= '2019-01'
)
SELECT ano, tipo_bandeira, COUNT(*) AS coletas, ROUND(AVG(desvio), 2) AS desvio_medio
FROM base
GROUP BY ano, tipo_bandeira
ORDER BY ano, tipo_bandeira;

-- nome: bandeira_12m
-- Mesma comparação, por bandeira, nos últimos 12 meses.
WITH base AS (
    SELECT bandeira, cnpj, preco_venda,
           preco_venda - AVG(preco_venda) OVER (PARTITION BY municipio, mes) AS desvio
    FROM coletas_rs
    WHERE mes >= :inicio_12m
)
SELECT bandeira, COUNT(*) AS coletas, COUNT(DISTINCT cnpj) AS revendas,
       ROUND(AVG(preco_venda), 2) AS preco_medio, ROUND(AVG(desvio), 2) AS desvio_medio
FROM base
GROUP BY bandeira
HAVING COUNT(*) >= 100
ORDER BY desvio_medio;

-- nome: margem_revenda_municipio
-- Margem por revenda (venda menos compra) enquanto a ANP coletou o preço de compra:
-- de janeiro de 2018 a agosto de 2020.
SELECT municipio, COUNT(*) AS coletas,
       ROUND(AVG(preco_compra), 2) AS compra,
       ROUND(AVG(preco_venda), 2) AS venda,
       ROUND(AVG(margem), 2) AS margem
FROM coletas_rs
WHERE margem IS NOT NULL
GROUP BY municipio
HAVING COUNT(*) >= 100
ORDER BY margem;

-- nome: margem_revenda_ano
SELECT substr(mes, 1, 4) AS ano, COUNT(*) AS coletas,
       ROUND(AVG(margem), 2) AS margem_media,
       ROUND(AVG(margem / preco_venda) * 100, 1) AS pct_do_preco
FROM coletas_rs
WHERE margem IS NOT NULL
GROUP BY ano
ORDER BY ano;

-- nome: sazonalidade_preco
-- Índice sazonal do preço: mês dividido pela média móvel de 12 meses ao redor dele
-- (100 = sem efeito do mês). A média móvel retira a tendência de alta, que de outro
-- modo faria todo fim de ano parecer mais caro que o começo.
WITH mensal AS (
    SELECT mes, substr(mes, 6, 2) AS mes_do_ano, AVG(preco_venda) AS valor
    FROM coletas_rs
    GROUP BY mes
), suavizado AS (
    SELECT mes_do_ano, valor,
           AVG(valor) OVER (ORDER BY mes ROWS BETWEEN 6 PRECEDING AND 5 FOLLOWING) AS media_movel,
           COUNT(*) OVER (ORDER BY mes ROWS BETWEEN 6 PRECEDING AND 5 FOLLOWING) AS meses_na_janela
    FROM mensal
)
SELECT mes_do_ano, ROUND(AVG(100.0 * valor / media_movel), 1) AS indice
FROM suavizado
WHERE meses_na_janela = 12
GROUP BY mes_do_ano
ORDER BY mes_do_ano;

-- nome: sazonalidade_volume
-- Mesmo índice para o volume de P13 vendido no RS.
WITH suavizado AS (
    SELECT mes_do_ano, mil_ton AS valor,
           AVG(mil_ton) OVER (ORDER BY ano, mes_do_ano ROWS BETWEEN 6 PRECEDING AND 5 FOLLOWING) AS media_movel,
           COUNT(*) OVER (ORDER BY ano, mes_do_ano ROWS BETWEEN 6 PRECEDING AND 5 FOLLOWING) AS meses_na_janela
    FROM vendas_p13_rs
)
SELECT printf('%02d', mes_do_ano) AS mes_do_ano, ROUND(AVG(100.0 * valor / media_movel), 1) AS indice
FROM suavizado
WHERE meses_na_janela = 12
GROUP BY mes_do_ano
ORDER BY mes_do_ano;

-- nome: volume_anual
SELECT ano, ROUND(SUM(mil_ton), 1) AS mil_ton, COUNT(*) AS meses
FROM vendas_p13_rs
GROUP BY ano
ORDER BY ano;

-- nome: indices_base100
-- Preço e parcelas do P13 no RS contra o IPCA, todos em índice com jan/2018 = 100.
-- Mostra quem subiu mais e quem subiu menos que a inflação.
WITH c AS (
    SELECT mes,
           MAX(CASE WHEN componente = 'preco_consumidor' THEN valor END) AS consumidor,
           MAX(CASE WHEN componente = 'produtor_com_tributos_federais' THEN valor END) AS produtor,
           MAX(CASE WHEN componente = 'icms' THEN valor END) AS icms,
           MAX(CASE WHEN componente = 'margem_distribuicao' THEN valor END) AS distribuicao,
           MAX(CASE WHEN componente = 'margem_revenda' THEN valor END) AS revenda
    FROM composicao
    WHERE local = 'Rio Grande do Sul'
    GROUP BY mes
), base AS (
    SELECT c.*, i.indice AS ipca FROM c JOIN ipca i USING (mes) WHERE mes = '2018-01'
)
SELECT c.mes,
       ROUND(100.0 * i.indice / base.ipca, 1) AS ipca,
       ROUND(100.0 * c.consumidor / base.consumidor, 1) AS consumidor,
       ROUND(100.0 * c.produtor / base.produtor, 1) AS produtor,
       ROUND(100.0 * c.icms / base.icms, 1) AS icms,
       ROUND(100.0 * c.distribuicao / base.distribuicao, 1) AS distribuicao,
       ROUND(100.0 * c.revenda / base.revenda, 1) AS revenda
FROM c JOIN ipca i USING (mes), base
ORDER BY c.mes;

-- nome: variacao_real
-- Variação de cada parcela entre o primeiro e o último mês com dados, nominal e
-- descontada a inflação. Real = (1 + nominal) / (1 + IPCA) - 1.
WITH limites AS (
    SELECT MIN(mes) AS inicio, MAX(mes) AS fim FROM composicao
    WHERE local = 'Rio Grande do Sul' AND componente = 'margem_revenda' AND valor IS NOT NULL
), inflacao AS (
    SELECT (SELECT indice FROM ipca WHERE mes = fim) / (SELECT indice FROM ipca WHERE mes = inicio) AS fator
    FROM limites
)
SELECT c.componente,
       MAX(CASE WHEN c.mes = l.inicio THEN c.valor END) AS valor_inicial,
       MAX(CASE WHEN c.mes = l.fim THEN c.valor END) AS valor_final,
       ROUND(100.0 * (MAX(CASE WHEN c.mes = l.fim THEN c.valor END) / MAX(CASE WHEN c.mes = l.inicio THEN c.valor END) - 1), 1) AS var_nominal_pct,
       ROUND(100.0 * (f.fator - 1), 1) AS ipca_pct,
       ROUND(100.0 * (MAX(CASE WHEN c.mes = l.fim THEN c.valor END) / MAX(CASE WHEN c.mes = l.inicio THEN c.valor END) / f.fator - 1), 1) AS var_real_pct,
       ROUND(MAX(CASE WHEN c.mes = l.inicio THEN c.valor END) * f.fator, 2) AS valor_inicial_corrigido,
       l.inicio, l.fim
FROM composicao c, limites l, inflacao f
WHERE c.local = 'Rio Grande do Sul'
  AND c.componente IN ('preco_consumidor', 'produtor_com_tributos_federais', 'icms', 'margem_distribuicao', 'margem_revenda')
GROUP BY c.componente
ORDER BY var_real_pct;

-- nome: composicao_real_rs
-- Parcelas do preço no RS em reais do último mês (corrigidas pelo IPCA).
WITH ref AS (
    SELECT indice FROM ipca WHERE mes = (SELECT MAX(mes) FROM composicao WHERE local = 'Rio Grande do Sul')
)
SELECT c.mes,
       ROUND(MAX(CASE WHEN componente = 'produtor_com_tributos_federais' THEN valor END) * ref.indice / i.indice, 2) AS produtor,
       ROUND(MAX(CASE WHEN componente = 'icms' THEN valor END) * ref.indice / i.indice, 2) AS icms,
       ROUND(MAX(CASE WHEN componente = 'margem_distribuicao' THEN valor END) * ref.indice / i.indice, 2) AS distribuicao,
       ROUND(MAX(CASE WHEN componente = 'margem_revenda' THEN valor END) * ref.indice / i.indice, 2) AS revenda,
       ROUND(MAX(CASE WHEN componente = 'preco_consumidor' THEN valor END) * ref.indice / i.indice, 2) AS consumidor
FROM composicao c JOIN ipca i USING (mes), ref
WHERE c.local = 'Rio Grande do Sul'
GROUP BY c.mes
ORDER BY c.mes;

-- nome: reajuste_anual_vs_ipca
-- Variação do preço ao consumidor no RS de dezembro a dezembro, contra o IPCA do ano.
-- O ano corrente vai de dezembro até o último mês com dados.
WITH p AS (
    SELECT c.mes, c.valor AS preco, i.indice AS ipca
    FROM composicao c JOIN ipca i USING (mes)
    WHERE c.local = 'Rio Grande do Sul' AND c.componente = 'preco_consumidor' AND c.valor IS NOT NULL
), fim_de_ano AS (
    SELECT substr(mes, 1, 4) AS ano, MAX(mes) AS mes FROM p GROUP BY ano
)
SELECT f.ano, atual.mes AS ate,
       ROUND(100.0 * (atual.preco / anterior.preco - 1), 1) AS glp_pct,
       ROUND(100.0 * (atual.ipca / anterior.ipca - 1), 1) AS ipca_pct,
       ROUND(100.0 * (atual.preco / anterior.preco - 1) - 100.0 * (atual.ipca / anterior.ipca - 1), 1) AS diferenca_pp
FROM fim_de_ano f
JOIN p atual ON atual.mes = f.mes
JOIN p anterior ON anterior.mes = (CAST(f.ano AS INTEGER) - 1) || '-12'
ORDER BY f.ano;

-- nome: composicao_real_anual
-- Média anual de cada parcela no RS, em reais do último mês (IPCA). A média do ano
-- suaviza a divisão entre ICMS e margem de distribuição, que oscila de um mês para
-- outro até 2022 por causa da forma de recolhimento do imposto.
WITH ref AS (
    SELECT indice FROM ipca WHERE mes = (SELECT MAX(mes) FROM composicao WHERE local = 'Rio Grande do Sul')
), real AS (
    SELECT substr(c.mes, 1, 4) AS ano, c.mes, c.componente, c.valor * ref.indice / i.indice AS valor
    FROM composicao c JOIN ipca i USING (mes), ref
    WHERE c.local = 'Rio Grande do Sul'
)
SELECT ano, COUNT(DISTINCT mes) AS meses,
       ROUND(AVG(CASE WHEN componente = 'produtor_com_tributos_federais' THEN valor END), 2) AS produtor,
       ROUND(AVG(CASE WHEN componente = 'icms' THEN valor END), 2) AS icms,
       ROUND(AVG(CASE WHEN componente = 'margem_distribuicao' THEN valor END), 2) AS distribuicao,
       ROUND(AVG(CASE WHEN componente = 'margem_revenda' THEN valor END), 2) AS revenda,
       ROUND(AVG(CASE WHEN componente = 'preco_consumidor' THEN valor END), 2) AS consumidor
FROM real
GROUP BY ano
ORDER BY ano;
