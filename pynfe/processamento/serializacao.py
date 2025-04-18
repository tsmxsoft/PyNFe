# -*- coding: utf-8 -*-
from pynfe.entidades import NotaFiscal
from pynfe.utils import etree, so_numeros, obter_municipio_por_codigo, \
    obter_pais_por_codigo, obter_municipio_e_codigo, formatar_decimal, \
    remover_acentos, obter_uf_por_codigo, obter_codigo_por_municipio
from pynfe.utils.flags import CODIGOS_ESTADOS, VERSAO_PADRAO, NAMESPACE_NFE, NAMESPACE_SIG, VERSAO_QRCODE
from pynfe.utils.webservices import NFCE
import base64
import hashlib
from datetime import datetime
import re
import six
import traceback
from decimal import Decimal


class Serializacao(object):
    """Classe abstrata responsavel por fornecer as funcionalidades basicas para
    exportacao e importacao de Notas Fiscais eletronicas para formatos serializados
    de arquivos. Como XML, JSON, binario, etc.

    Nao deve ser instanciada diretamente!"""

    _fonte_dados = None
    _ambiente = 1           # 1 = Produção, 2 = Homologação
    _contingencia = None    # Justificativa da entrada em contingência (min 20, max 256 caracteres)
    _so_cpf = False         # Destinatário com apenas o cpf do cliente
    _nome_aplicacao = 'PyNFe'

    def __new__(cls, *args, **kwargs):
        if cls == Serializacao:
            raise Exception('Esta classe nao pode ser instanciada diretamente!')
        else:
            return super(Serializacao, cls).__new__(cls)

    def __init__(self, fonte_dados, homologacao=False, contingencia=None, so_cpf=False):
        self._fonte_dados = fonte_dados
        self._ambiente = homologacao and 2 or 1
        self._contingencia = contingencia
        self._so_cpf = so_cpf

    def exportar(self, destino, **kwargs):
        """Gera o(s) arquivo(s) de exportacao a partir da Nofa Fiscal eletronica
        ou lista delas."""
        raise NotImplementedError

    def importar(self, origem):
        """Fabrica que recebe o caminho ou objeto de origem e instancia os objetos
        da PyNFe"""
        raise NotImplementedError


class SerializacaoXML(Serializacao):
    """ Classe de serialização do arquivo xml """

    _versao = VERSAO_PADRAO

    def exportar(self, destino=None, retorna_string=False, limpar=True, **kwargs):
        """Gera o(s) arquivo(s) de Nota Fiscal eletronica no padrao oficial da SEFAZ
        e Receita Federal, para ser(em) enviado(s) para o webservice ou para ser(em)
        armazenado(s) em cache local.
        @param destino -
        @param retorna_string - Retorna uma string para debug.
        @param limpar - Limpa a fonte de dados para não gerar xml com dados duplicados.
        """
        try:
            # No raiz do XML de saida
            raiz = etree.Element('NFe', xmlns=NAMESPACE_NFE)

            # Carrega lista de Notas Fiscais
            notas_fiscais = self._fonte_dados.obter_lista(_classe=NotaFiscal, **kwargs)

            for nf in notas_fiscais:
                raiz.append(self._serializar_nota_fiscal(nf, retorna_string=False))

            if retorna_string:
                return etree.tostring(raiz, encoding="unicode", pretty_print=False)
            else:
                return raiz
        except Exception as e:
            raise e
        finally:
            if limpar:
                self._fonte_dados.limpar_dados()

    def importar(self, origem):
        """Cria as instancias do PyNFe a partir de arquivos XML no formato padrao da
        SEFAZ e Receita Federal."""

        raise Exception('Metodo nao implementado')

    def _serializar_emitente(self, emitente, tag_raiz='emit', retorna_string=True):
        raiz = etree.Element(tag_raiz)

        # Dados do emitente
        etree.SubElement(raiz, 'CNPJ').text = so_numeros(emitente.cnpj)
        etree.SubElement(raiz, 'xNome').text = emitente.razao_social
        etree.SubElement(raiz, 'xFant').text = emitente.nome_fantasia
        # Endereço
        endereco = etree.SubElement(raiz, 'enderEmit')
        etree.SubElement(endereco, 'xLgr').text = emitente.endereco_logradouro
        etree.SubElement(endereco, 'nro').text = emitente.endereco_numero
        if emitente.endereco_complemento:
            etree.SubElement(endereco, 'xCpl').text = emitente.endereco_complemento
        etree.SubElement(endereco, 'xBairro').text = emitente.endereco_bairro
        etree.SubElement(endereco, 'cMun').text = obter_codigo_por_municipio(
            emitente.endereco_municipio, emitente.endereco_uf)
        etree.SubElement(endereco, 'xMun').text = emitente.endereco_municipio
        etree.SubElement(endereco, 'UF').text = emitente.endereco_uf
        etree.SubElement(endereco, 'CEP').text = so_numeros(emitente.endereco_cep)
        etree.SubElement(endereco, 'cPais').text = emitente.endereco_pais
        etree.SubElement(endereco, 'xPais').text = obter_pais_por_codigo(emitente.endereco_pais)
        if emitente.endereco_telefone:
            etree.SubElement(endereco, 'fone').text = emitente.endereco_telefone
        etree.SubElement(raiz, 'IE').text = emitente.inscricao_estadual
        # Apenas NF-e
        if emitente.inscricao_estadual_subst_tributaria:
            etree.SubElement(raiz, 'IEST').text = emitente.inscricao_estadual_subst_tributaria
        # Inscricao Municipal
        if emitente.inscricao_municipal:
            etree.SubElement(raiz, 'IM').text = emitente.inscricao_municipal
            # Campo Opcional. Pode ser informado quando a Inscrição Municipal (id:C19) for informada.
            if emitente.cnae_fiscal:
                etree.SubElement(raiz, 'CNAE').text = emitente.cnae_fiscal
        etree.SubElement(raiz, 'CRT').text = emitente.codigo_de_regime_tributario
        if retorna_string:
            return etree.tostring(raiz, encoding="unicode", pretty_print=True)
        else:
            return raiz

    def _serializar_cliente(self, cliente, modelo, tag_raiz='dest', retorna_string=True):
        raiz = etree.Element(tag_raiz)

        # Dados do cliente (distinatario)
        etree.SubElement(raiz, cliente.tipo_documento).text = so_numeros(cliente.numero_documento)
        if not self._so_cpf:
            if cliente.razao_social:
                etree.SubElement(raiz, 'xNome').text = cliente.razao_social
            endereco = etree.SubElement(raiz, 'enderDest')
            etree.SubElement(endereco, 'xLgr').text = cliente.endereco_logradouro
            etree.SubElement(endereco, 'nro').text = cliente.endereco_numero
            if cliente.endereco_complemento:
                etree.SubElement(endereco, 'xCpl').text = cliente.endereco_complemento
            etree.SubElement(endereco, 'xBairro').text = cliente.endereco_bairro
            etree.SubElement(endereco, 'cMun').text = obter_codigo_por_municipio(
                cliente.endereco_municipio, cliente.endereco_uf)
            etree.SubElement(endereco, 'xMun').text = cliente.endereco_municipio
            etree.SubElement(endereco, 'UF').text = cliente.endereco_uf
            etree.SubElement(endereco, 'CEP').text = so_numeros(cliente.endereco_cep)
            etree.SubElement(endereco, 'cPais').text = cliente.endereco_pais
            etree.SubElement(endereco, 'xPais').text = obter_pais_por_codigo(cliente.endereco_pais)
            if cliente.endereco_telefone:
                etree.SubElement(endereco, 'fone').text = cliente.endereco_telefone
        #Indicador da IE do destinatário: 1 – Contribuinte ICMSpagamento à vista; 2 – Contribuinte isento de inscrição; 9 – Não Contribuinte
        if cliente.indicador_ie == 9:
            # 9 – Não Contribuinte
            etree.SubElement(raiz, 'indIEDest').text = '9'
        elif (cliente.indicador_ie == 2 or cliente.isento_icms) or cliente.inscricao_estadual.upper() == 'ISENTO':
            etree.SubElement(raiz, 'indIEDest').text = '2'
        else:
            # Indicador da IE do destinatário: 1 – Contribuinte ICMSpagamento à vista;
            etree.SubElement(raiz, 'indIEDest').text = str(cliente.indicador_ie)
            etree.SubElement(raiz, 'IE').text = cliente.inscricao_estadual
        # Suframa
        if cliente.inscricao_suframa:
            etree.SubElement(raiz, 'ISUF').text = cliente.inscricao_suframa
        # Inscrição Municipal do tomador do serviço
        if cliente.inscricao_municipal:
            etree.SubElement(raiz, 'IM').text = cliente.inscricao_municipal
        # E-mail
        if cliente.email:
            etree.SubElement(raiz, 'email').text = cliente.email
        if retorna_string:
            return etree.tostring(raiz, encoding="unicode", pretty_print=True)
        else:
            return raiz

    def _serializar_autxml(self,notafiscal,tag_raiz='autXML',retorna_string=True):
        # Dados pessoas autorizadas 
        # list object [tipodoc{string},cpfcnpj{string}]
        pessoas = getattr(notafiscal,'autXML',[])
        if pessoas:
            raiz = etree.Element(tag_raiz)
            for p in pessoas:
                etree.SubElement(raiz, p.tipodoc).text = p.cpfcnpj

            if retorna_string:
                return etree.tostring(raiz, encoding="unicode", pretty_print=True)

        return raiz

    def _serializar_transportadora(self, transportadora, tag_raiz='transporta', retorna_string=True):
        raiz = etree.Element(tag_raiz)

        # Dados da transportadora
        etree.SubElement(raiz, transportadora.tipo_documento.upper()).text = so_numeros(transportadora.numero_documento)
        etree.SubElement(raiz, 'xNome').text = transportadora.razao_social
        etree.SubElement(raiz, 'IE').text = transportadora.inscricao_estadual
        # Endereço
        etree.SubElement(raiz, 'xEnder').text = transportadora.endereco_logradouro
        etree.SubElement(raiz, 'xMun').text = transportadora.endereco_municipio
        etree.SubElement(raiz, 'UF').text = transportadora.endereco_uf

        if retorna_string:
            return etree.tostring(raiz, encoding="unicode", pretty_print=True)
        else:
            return raiz

    def _serializar_entrega_retirada(self, entrega_retirada, tag_raiz='entrega', retorna_string=True):
        raiz = etree.Element(tag_raiz)

        # Dados da entrega/retirada
        etree.SubElement(raiz, entrega_retirada.tipo_documento).text = so_numeros(entrega_retirada.numero_documento)

        # Endereço
        etree.SubElement(raiz, 'xLgr').text = entrega_retirada.endereco_logradouro
        etree.SubElement(raiz, 'nro').text = entrega_retirada.endereco_numero
        etree.SubElement(raiz, 'xCpl').text = entrega_retirada.endereco_complemento
        etree.SubElement(raiz, 'xBairro').text = entrega_retirada.endereco_bairro
        etree.SubElement(raiz, 'cMun').text = entrega_retirada.endereco_municipio
        etree.SubElement(raiz, 'xMun').text = obter_municipio_por_codigo(
                entrega_retirada.endereco_municipio, entrega_retirada.endereco_uf,
                )
        etree.SubElement(raiz, 'UF').text = entrega_retirada.endereco_uf

        if retorna_string:
            return etree.tostring(raiz, encoding="unicode", pretty_print=True)
        else:
            return raiz

    def _serializar_produto_servico(self, produto_servico, modelo, tag_raiz='det', retorna_string=True, nota_fiscal=None):
        raiz = etree.Element(tag_raiz)

        # Produto
        prod = etree.SubElement(raiz, 'prod')
        etree.SubElement(prod, 'cProd').text = str(produto_servico.codigo)
        etree.SubElement(prod, 'cEAN').text = produto_servico.ean
        etree.SubElement(prod, 'xProd').text = produto_servico.descricao
        etree.SubElement(prod, 'NCM').text = produto_servico.ncm
        # Codificação opcional que detalha alguns NCM. Formato: duas letras maiúsculas e 4 algarismos.
        # Se a mercadoria se enquadrar em mais de uma codificação, informar até 8 codificações principais.
        #etree.SubElement(prod, 'NVE').text = ''
        #
        """ Código Especificador da Substituição Tributária – CEST, que estabelece a sistemática de uniformização e identificação das mercadorias e bens passíveis de
        sujeição aos regimes de substituição tributária e de antecipação de recolhimento do ICMS. """
        if produto_servico.cest and produto_servico.icms_modalidade in ['41', '60', '70', '201', '400', '500']:
            etree.SubElement(prod, 'CEST').text = produto_servico.cest

        if produto_servico.cbenef:
            etree.SubElement(prod, 'cBenef').text = produto_servico.cbenef
        
        etree.SubElement(prod, 'CFOP').text = produto_servico.cfop
        etree.SubElement(prod, 'uCom').text = produto_servico.unidade_comercial
        etree.SubElement(prod, 'qCom').text = str(produto_servico.quantidade_comercial or 0)
        etree.SubElement(prod, 'vUnCom').text = str('{:.4f}').format(produto_servico.valor_unitario_comercial or 0)
        etree.SubElement(prod, 'vProd').text = str('{:.2f}').format(produto_servico.valor_total_bruto or 0)
        etree.SubElement(prod, 'cEANTrib').text = produto_servico.ean_tributavel
        etree.SubElement(prod, 'uTrib').text = produto_servico.unidade_tributavel
        etree.SubElement(prod, 'qTrib').text = str(produto_servico.quantidade_tributavel)
        etree.SubElement(prod, 'vUnTrib').text = '{:.4f}'.format(produto_servico.valor_unitario_tributavel or 0)

        if produto_servico.total_frete:
            etree.SubElement(prod, 'vFrete').text = '{:.2f}'.format(produto_servico.total_frete)

        if produto_servico.desconto:
            etree.SubElement(prod, 'vDesc').text = '{:.2f}'.format(produto_servico.desconto)

        if produto_servico.outras_despesas_acessorias:
            etree.SubElement(prod, 'vOutro').text = '{:.2f}'.format(produto_servico.outras_despesas_acessorias)

        """ Indica se valor do Item (vProd) entra no valor total da NF-e (vProd)
            0=Valor do item (vProd) não compõe o valor total da NF-e
            1=Valor do item (vProd) compõe o valor total da NF-e (vProd) (v2.0)
        """
        etree.SubElement(prod, 'indTot').text = str(produto_servico.ind_total)

        try:
            if produto_servico.xped:
                etree.SubElement(prod, 'xPed').text = str(produto_servico.xped)
            if produto_servico.nitemped:
                etree.SubElement(prod, 'nItemPed').text = str(produto_servico.nitemped)
        except:
            traceback.print_exc()

        """ Informação de interesse do emissor para controle do B2B.(v2.0) """
        # Número do Pedido de Compra. Tam 1-15
        if produto_servico.numero_pedido:
            etree.SubElement(prod, 'xPed').text = str(produto_servico.numero_pedido)
        # Item do Pedido de Compra. Tam 6
        if produto_servico.numero_item:
            etree.SubElement(prod, 'nItemPed').text = str(produto_servico.numero_item)

        # Imposto
        imposto = etree.SubElement(raiz, 'imposto')

        # nFCI
        if produto_servico.nfci:
            etree.SubElement(prod, 'nFCI').text = produto_servico.nfci

        # Lei da transparencia
        # Tributos aprox por item
        if produto_servico.valor_tributos_aprox:
            etree.SubElement(imposto, 'vTotTrib').text = str(produto_servico.valor_tributos_aprox)

        if not produto_servico.issqn_valor_base_calculo:
            ### ICMS
            icms = etree.SubElement(imposto, 'ICMS')
            icms_csosn = ('102', '103', '300', '400')
            if produto_servico.icms_modalidade in icms_csosn:
                icms_item = etree.SubElement(icms, 'ICMSSN102')
                etree.SubElement(icms_item, 'orig').text = str(produto_servico.icms_origem)
                etree.SubElement(icms_item, 'CSOSN').text = produto_servico.icms_csosn
            elif produto_servico.icms_modalidade == '101':
                icms_item = etree.SubElement(icms, 'ICMSSN'+produto_servico.icms_modalidade)
                etree.SubElement(icms_item, 'orig').text = str(produto_servico.icms_origem)
                etree.SubElement(icms_item, 'CSOSN').text = produto_servico.icms_csosn
                etree.SubElement(icms_item, 'pCredSN').text = str(produto_servico.icms_aliquota)       # Alíquota aplicável de cálculo do crédito (Simples Nacional).
                etree.SubElement(icms_item, 'vCredICMSSN').text = '{:.2f}'.format(produto_servico.icms_credito or 0)  # Valor crédito do ICMS que pode ser aproveitado nos termos do art. 23 da LC 123 (Simples Nacional)
            elif produto_servico.icms_modalidade == '201' and int(nota_fiscal.emitente.codigo_de_regime_tributario) == 1:
                icms_item = etree.SubElement(icms, 'ICMSSN201')
                etree.SubElement(icms_item, 'orig').text = str(produto_servico.icms_origem)
                etree.SubElement(icms_item, 'CSOSN').text = produto_servico.icms_csosn
                etree.SubElement(icms_item, 'modBCST').text = str(produto_servico.icms_modalidade_determinacao_bc)
                etree.SubElement(icms_item, 'pMVAST').text =  '{:.2f}'.format(produto_servico.icms_st_percentual_adicional or 0)
                etree.SubElement(icms_item, 'pRedBCST').text = '{:.2f}'.format(produto_servico.icms_st_valor_base_calculo or 0)
                etree.SubElement(icms_item, 'vBCST').text = '{:.2f}'.format(produto_servico.icms_st_valor_base_calculo or 0)
                etree.SubElement(icms_item, 'pICMSST').text = '{:.4f}'.format(produto_servico.icms_st_aliquota or 0)
                etree.SubElement(icms_item, 'vICMSST').text = '{:.2f}'.format(produto_servico.icms_st_valor or 0)
                # NT_2016_002
                # Inclusão das regras de validação N17b-20, N23b-20 e N27b-20 que impedem que seja informado zero como percentual de FCP ou FCP ST.
                # Os campos relativos ao Fundo de Combate à Pobreza só devem ser informados se o produto estiver sujeito a incidência do mesmo.
                if produto_servico.fcp_valor:
                    etree.SubElement(icms_item, 'vBCFCP').text = '{:.2f}'.format(produto_servico.fcp_base_calculo or 0)  # Base de calculo FCP
                    etree.SubElement(icms_item, 'pFCP').text = '{:.2f}'.format(produto_servico.fcp_percentual or 0)  # Percentual FCP
                    etree.SubElement(icms_item, 'vFCP').text = '{:.2f}'.format(produto_servico.fcp_valor or 0)  # Valor Fundo Combate a Pobreza
                etree.SubElement(icms_item, 'pCredSN').text = str(produto_servico.icms_aliquota)       # Alíquota aplicável de cálculo do crédito (Simples Nacional).
                etree.SubElement(icms_item, 'vCredICMSSN').text = '{:.2f}'.format(produto_servico.icms_credito or 0)  # Valor crédito do ICMS que pode ser aproveitado nos termos do art. 23 da LC 123 (Simples Nacional)

            elif produto_servico.icms_modalidade == '900':
                icms_item = etree.SubElement(icms, 'ICMSSN900')
                etree.SubElement(icms_item, 'orig').text = str(produto_servico.icms_origem)
                etree.SubElement(icms_item, 'CSOSN').text = produto_servico.icms_csosn

                etree.SubElement(icms_item, 'modBC').text = str(produto_servico.icms_modalidade_determinacao_bc)
                etree.SubElement(icms_item, 'vBC').text = '{:.2f}'.format(produto_servico.icms_valor_base_calculo or 0)  # Valor da BC do ICMS
                etree.SubElement(icms_item, 'pRedBC').text = '{:.4f}'.format(produto_servico.icms_percentual_reducao_bc or 0)  # Percentual da Redução de BC
                etree.SubElement(icms_item, 'pICMS').text = '{:.2f}'.format(produto_servico.icms_aliquota or 0)          # Alíquota do imposto
                etree.SubElement(icms_item, 'vICMS').text = '{:.2f}'.format(produto_servico.icms_valor or 0) # Valor do ICMS

                etree.SubElement(icms_item, 'modBCST').text = str(produto_servico.icms_st_modalidade_determinacao_bc or 0)
                etree.SubElement(icms_item, 'pMVAST').text =  '{:.4f}'.format(produto_servico.icms_st_percentual_adicional or 0)
                etree.SubElement(icms_item, 'pRedBCST').text = '{:.4f}'.format(produto_servico.icms_st_percentual_reducao_bc or 0)
                etree.SubElement(icms_item, 'vBCST').text = '{:.2f}'.format(produto_servico.icms_st_valor_base_calculo or 0)
                etree.SubElement(icms_item, 'pICMSST').text = '{:.4f}'.format(produto_servico.icms_st_aliquota or 0)
                etree.SubElement(icms_item, 'vICMSST').text = '{:.2f}'.format(produto_servico.icms_st_valor or 0)
            elif produto_servico.icms_modalidade == 'ST':
                icms_item = etree.SubElement(icms, 'ICMS'+produto_servico.icms_modalidade)
                etree.SubElement(icms_item, 'orig').text = str(produto_servico.icms_origem)
                etree.SubElement(icms_item, 'CST').text = '41'          # Nao tributado
                etree.SubElement(icms_item, 'vBCSTRet').text = ''       # Informar o valor da BC do ICMS ST retido na UF remetente
                etree.SubElement(icms_item, 'vICMSSTRet').text = ''     # Informar o valor do ICMS ST retido na UF remetente
                etree.SubElement(icms_item, 'vBCSTDest').text = ''      # Informar o valor da BC do ICMS ST da UF destino
                etree.SubElement(icms_item, 'vICMSSTDest').text = ''    # Informar o valor do ICMS ST da UF destino
            elif produto_servico.icms_modalidade == '500':
                icms_item = etree.SubElement(icms, 'ICMSSN'+produto_servico.icms_modalidade)
                etree.SubElement(icms_item, 'orig').text = str(produto_servico.icms_origem)
                etree.SubElement(icms_item, 'CSOSN').text = produto_servico.icms_csosn

                if nota_fiscal and nota_fiscal.cliente_final and not produto_servico.icms_st_retido:
                    etree.SubElement(icms_item, 'vBCSTRet').text = '{:.2f}'.format(0)
                    etree.SubElement(icms_item, 'pST').text = '{:.4f}'.format(0)
                    etree.SubElement(icms_item, 'vICMSSubstituto').text = '{:.2f}'.format(produto_servico.icms_st_substituto or 0)
                    etree.SubElement(icms_item, 'vICMSSTRet').text = '{:.2f}'.format(0)

                    etree.SubElement(icms_item, 'pRedBCEfet').text = '{:.4f}'.format(produto_servico.icms_st_percentual_reducao_bc or 0)
                    etree.SubElement(icms_item, 'vBCEfet').text = '{:.2f}'.format(produto_servico.icms_st_valor_base_calculo or 0)
                    etree.SubElement(icms_item, 'pICMSEfet').text = '{:.4f}'.format(produto_servico.icms_st_aliquota or 0)
                    etree.SubElement(icms_item, 'vICMSEfet').text = '{:.2f}'.format(produto_servico.icms_st_valor or 0)

                else:
                    etree.SubElement(icms_item, 'vBCSTRet').text = '{:.2f}'.format(produto_servico.icms_st_valor_base_calculo or 0)
                    etree.SubElement(icms_item, 'pST').text = '{:.4f}'.format(produto_servico.icms_st_aliquota or 0)
                    etree.SubElement(icms_item, 'vICMSSubstituto').text = '{:.2f}'.format(produto_servico.icms_st_substituto)
                    etree.SubElement(icms_item, 'vICMSSTRet').text = '{:.2f}'.format(produto_servico.icms_st_valor)


            else: 
                if produto_servico.icms_modalidade in ["40","41","50"]:
                    icms_item = etree.SubElement(icms, 'ICMS40')
                    etree.SubElement(icms_item, 'orig').text = str(produto_servico.icms_origem)
                    etree.SubElement(icms_item, 'CST').text = produto_servico.icms_modalidade
                else:
                    ### OUTROS TIPOS DE ICMS (00,10,20,41)
                    icms_item = etree.SubElement(icms, 'ICMS'+produto_servico.icms_modalidade)
                    etree.SubElement(icms_item, 'orig').text = str(produto_servico.icms_origem)
                    etree.SubElement(icms_item, 'CST').text = produto_servico.icms_modalidade
                    # Modalidade de determinação da BC do ICMS: 0=Margem Valor Agregado (%); 1=Pauta (Valor); 2=Preço Tabelado Máx. (valor); 3=Valor da operação.
                    if produto_servico.icms_modalidade not in ['40','50']:
                        etree.SubElement(icms_item, 'modBC').text = str(produto_servico.icms_modalidade_determinacao_bc)
                    # 00=Tributada integralmente.
                    if produto_servico.icms_modalidade == '00':
                        etree.SubElement(icms_item, 'vBC').text = '{:.2f}'.format(produto_servico.icms_valor_base_calculo or 0)  # Valor da BC do ICMS
                        etree.SubElement(icms_item, 'pICMS').text = '{:.2f}'.format(produto_servico.icms_aliquota or 0)          # Alíquota do imposto
                        etree.SubElement(icms_item, 'vICMS').text = '{:.2f}'.format(produto_servico.icms_valor or 0) # Valor do ICMS
                    # 10=Tributada e com cobrança do ICMS por substituição tributária
                    elif produto_servico.icms_modalidade == '10':
                        etree.SubElement(icms_item, 'vBC').text = '{:.2f}'.format(produto_servico.icms_valor_base_calculo or 0)  # Valor da BC do ICMS
                        etree.SubElement(icms_item, 'pICMS').text = '{:.2f}'.format(produto_servico.icms_aliquota or 0)          # Alíquota do imposto
                        etree.SubElement(icms_item, 'vICMS').text = '{:.2f}'.format(produto_servico.icms_valor or 0) # Valor do ICMS
                        # Modalidade de determinação da BC do ICMS ST
                        # 0=Preço tabelado ou máximo sugerido; 1=Lista Negativa (valor);2=Lista Positiva (valor);3=Lista Neutra (valor);4=Margem Valor Agregado (%);5=Pauta (valor);
                        etree.SubElement(icms_item, 'modBCST').text = str(produto_servico.icms_st_modalidade_determinacao_bc or 0)
                        if produto_servico.icms_st_percentual_adicional:
                            etree.SubElement(icms_item, 'pMVAST').text = str(produto_servico.icms_st_percentual_adicional or 0) # Percentual da margem de valor Adicionado do ICMS S
                        if produto_servico.icms_st_percentual_reducao_bc:
                            etree.SubElement(icms_item, 'pRedBCST').text = str(produto_servico.icms_st_percentual_reducao_bc or 0) # APercentual da Redução de BC do ICMS ST
                        etree.SubElement(icms_item, 'vBCST').text = str(produto_servico.icms_st_valor_base_calculo or 0)
                        etree.SubElement(icms_item, 'pICMSST').text = str(produto_servico.icms_st_aliquota or 0)
                        etree.SubElement(icms_item, 'vICMSST').text = str(produto_servico.icms_st_valor or 0)
                    # 20=Com redução de base de cálculo
                    # 70=Tributação ICMS com redução de base de cálculo e cobrança do ICMS por substituição tributária
                    elif produto_servico.icms_modalidade in ['20','70']:
                        etree.SubElement(icms_item, 'pRedBC').text = '{:.4f}'.format(produto_servico.icms_percentual_reducao_bc or 0)  # Percentual da Redução de BC
                        etree.SubElement(icms_item, 'vBC').text = '{:.2f}'.format(produto_servico.icms_valor_base_calculo or 0)  # Valor da BC do ICMS
                        etree.SubElement(icms_item, 'pICMS').text = '{:.2f}'.format(produto_servico.icms_aliquota or 0)          # Alíquota do imposto
                        etree.SubElement(icms_item, 'vICMS').text = '{:.2f}'.format(produto_servico.icms_valor or 0)  # Valor do ICMS
                        if produto_servico.icms_modalidade == '70':
                            # Modalidade de determinação da BC do ICMS ST
                            # 0=Preço tabelado ou máximo sugerido; 1=Lista Negativa (valor);2=Lista Positiva (valor);3=Lista Neutra (valor);4=Margem Valor Agregado (%);5=Pauta (valor);
                            etree.SubElement(icms_item, 'modBCST').text = str(produto_servico.icms_st_modalidade_determinacao_bc or 0)
                            if produto_servico.icms_st_percentual_adicional:
                                etree.SubElement(icms_item, 'pMVAST').text = str(produto_servico.icms_st_percentual_adicional or 0) # Percentual da margem de valor Adicionado do ICMS S
                            if produto_servico.icms_st_percentual_reducao_bc:
                                etree.SubElement(icms_item, 'pRedBCST').text = str(produto_servico.icms_st_percentual_reducao_bc or 0) # APercentual da Redução de BC do ICMS ST
                            etree.SubElement(icms_item, 'vBCST').text = '{:.2f}'.format(produto_servico.icms_st_valor_base_calculo or 0)
                            etree.SubElement(icms_item, 'pICMSST').text = str(produto_servico.icms_st_aliquota or 0)
                            etree.SubElement(icms_item, 'vICMSST').text = '{:.2f}'.format(produto_servico.icms_st_valor or 0)
                        # NT_2016_002
                        # Inclusão das regras de validação N17b-20, N23b-20 e N27b-20 que impedem que seja informado zero como percentual de FCP ou FCP ST.
                        # Os campos relativos ao Fundo de Combate à Pobreza só devem ser informados se o produto estiver sujeito a incidência do mesmo.
                        if produto_servico.fcp_valor:
                            etree.SubElement(icms_item, 'vBCFCP').text = '{:.2f}'.format(produto_servico.fcp_base_calculo or 0)  # Base de calculo FCP
                            etree.SubElement(icms_item, 'pFCP').text = '{:.2f}'.format(produto_servico.fcp_percentual or 0)  # Percentual FCP
                            etree.SubElement(icms_item, 'vFCP').text = '{:.2f}'.format(produto_servico.fcp_valor or 0)  # Valor Fundo Combate a Pobreza
                    elif produto_servico.icms_modalidade == '30':
                        for child in icms_item.findall("modBC"):
                            icms_item.remove(child)
                        etree.SubElement(icms_item, 'modBCST').text = str(produto_servico.icms_st_modalidade_determinacao_bc or 0)
                        etree.SubElement(icms_item, 'vBCST').text = str(produto_servico.icms_st_valor_base_calculo or 0)
                        etree.SubElement(icms_item, 'pICMSST').text = str(produto_servico.icms_st_aliquota or 0)
                        etree.SubElement(icms_item, 'vICMSST').text = str(produto_servico.icms_st_valor or 0)
                    elif produto_servico.icms_modalidade == '51':
                        etree.SubElement(icms_item, 'pRedBC').text = '{:.4f}'.format(produto_servico.icms_percentual_reducao_bc or 0)  # Percentual da Redução de BC
                        etree.SubElement(icms_item, 'vBC').text = '{:.2f}'.format(produto_servico.icms_valor_base_calculo or 0)  # Valor da BC do ICMS
                        etree.SubElement(icms_item, 'pICMS').text = '{:.2f}'.format(produto_servico.icms_aliquota or 0)          # Alíquota do imposto
                        etree.SubElement(icms_item, 'vICMS').text = '{:.2f}'.format(produto_servico.icms_valor or 0)  # Valor do ICMS
                    elif produto_servico.icms_modalidade == '60':

                        for child in icms_item.findall("modBC"):
                            icms_item.remove(child)

                        if nota_fiscal and nota_fiscal.cliente_final and not produto_servico.icms_st_retido:
                            etree.SubElement(icms_item, 'vBCSTRet').text = '{:.2f}'.format(0)
                            etree.SubElement(icms_item, 'pST').text = '{:.4f}'.format(0)
                            etree.SubElement(icms_item, 'vICMSSubstituto').text = '{:.2f}'.format(produto_servico.icms_st_substituto or 0)
                            etree.SubElement(icms_item, 'vICMSSTRet').text = '{:.2f}'.format(0)

                            etree.SubElement(icms_item, 'pRedBCEfet').text = '{:.4f}'.format(produto_servico.icms_st_percentual_reducao_bc or 0)
                            etree.SubElement(icms_item, 'vBCEfet').text = '{:.2f}'.format(produto_servico.icms_st_valor_base_calculo or 0)
                            etree.SubElement(icms_item, 'pICMSEfet').text = '{:.4f}'.format(produto_servico.icms_st_aliquota or 0)
                            etree.SubElement(icms_item, 'vICMSEfet').text = '{:.2f}'.format(produto_servico.icms_st_valor or 0)

                        else:
                            etree.SubElement(icms_item, 'vBCSTRet').text = '{:.2f}'.format(produto_servico.icms_st_valor_base_calculo or 0)
                            etree.SubElement(icms_item, 'pST').text = '{:.4f}'.format(produto_servico.icms_st_aliquota or 0)
                            etree.SubElement(icms_item, 'vICMSSubstituto').text = '{:.2f}'.format(produto_servico.icms_st_substituto or 0)
                            etree.SubElement(icms_item, 'vICMSSTRet').text = '{:.2f}'.format(0)

                            #etree.SubElement(icms_item, 'pRedBCEfet').text = '{:.4f}'.format(0)
                            #etree.SubElement(icms_item, 'vBCEfet').text = '{:.2f}'.format(0)
                            #etree.SubElement(icms_item, 'pICMSEfet').text = '{:.4f}'.format(0)
                            #etree.SubElement(icms_item, 'vICMSEfet').text = '{:.2f}'.format(0)
                    elif produto_servico.icms_modalidade == '90':
                        etree.SubElement(icms_item, 'vBC').text = '{:.2f}'.format(produto_servico.icms_valor_base_calculo or 0)  # Valor da BC do ICMS
                        etree.SubElement(icms_item, 'pICMS').text = '{:.2f}'.format(produto_servico.icms_aliquota or 0)          # Alíquota do imposto
                        etree.SubElement(icms_item, 'vICMS').text = '{:.2f}'.format(produto_servico.icms_valor or 0) # Valor do ICMS
                        # Modalidade de determinação da BC do ICMS ST
                        # 0=Preço tabelado ou máximo sugerido; 1=Lista Negativa (valor);2=Lista Positiva (valor);3=Lista Neutra (valor);4=Margem Valor Agregado (%);5=Pauta (valor);
                        etree.SubElement(icms_item, 'modBCST').text = str(produto_servico.icms_st_modalidade_determinacao_bc or 0)
                        etree.SubElement(icms_item, 'vBCST').text = str(produto_servico.icms_st_valor_base_calculo or 0)
                        etree.SubElement(icms_item, 'pICMSST').text = str(produto_servico.icms_st_aliquota or 0)
                        etree.SubElement(icms_item, 'vICMSST').text = str(produto_servico.icms_st_valor or 0)

                    


        # ISSQN
        if produto_servico.issqn_valor_base_calculo:
            issqn = etree.SubElement(imposto, 'ISSQN')
            etree.SubElement(issqn, 'vBC').text = '{:.2f}'.format(produto_servico.issqn_valor_base_calculo or 0)
            etree.SubElement(issqn, 'vAliq').text = '{:.2f}'.format(produto_servico.issqn_aliquota or 0)
            etree.SubElement(issqn, 'vISSQN').text = '{:.2f}'.format(produto_servico.issqn_valor or 0)
            etree.SubElement(issqn, 'cMunFG').text = produto_servico.issqn_municipio
            etree.SubElement(issqn, 'cListServ').text = produto_servico.issqn_lista_servico
            etree.SubElement(issqn, 'indISS').text = produto_servico.issqn_indiss
            etree.SubElement(issqn, 'indIncentivo').text = produto_servico.issqn_indincentivo


        # IPI
        if str(produto_servico.icms_modalidade) not in ["41"]:
            if not produto_servico.issqn_valor_base_calculo:
                if produto_servico.ipi_codigo_enquadramento:
                    ipi = etree.SubElement(imposto, 'IPI')
                    etree.SubElement(ipi, 'cEnq').text = produto_servico.ipi_codigo_enquadramento
                    if produto_servico.ipi_situacao_tributaria:
                        if str(produto_servico.ipi_situacao_tributaria) in ["00", "49", "50", "99"]:
                            ipitrib = etree.SubElement(ipi, 'IPITrib')
                            etree.SubElement(ipitrib, 'CST').text = produto_servico.ipi_situacao_tributaria
                            etree.SubElement(ipitrib, 'vBC').text = '{:.2f}'.format(produto_servico.ipi_valor_base_calculo or 0)
                            etree.SubElement(ipitrib, 'pIPI').text = '{:.2f}'.format(produto_servico.ipi_aliquota or 0)
                            etree.SubElement(ipitrib, 'vIPI').text = '{:.2f}'.format(produto_servico.ipi_valor_ipi or 0)
                        else:
                            ipint = etree.SubElement(ipi, 'IPINT')
                            etree.SubElement(ipint, 'CST').text = produto_servico.ipi_situacao_tributaria
        # apenas nfe
        if modelo == 55:
            ## PIS
            pisnt = ('04','05','06','07','08','09')
            pis = etree.SubElement(imposto, 'PIS')
            if produto_servico.pis_modalidade in pisnt:
                pis_item = etree.SubElement(pis, 'PISNT')
                etree.SubElement(pis_item, 'CST').text = produto_servico.pis_modalidade
            elif produto_servico.pis_modalidade == '01' or produto_servico.pis_modalidade == '02':
                pis_item = etree.SubElement(pis, 'PISAliq')
                etree.SubElement(pis_item, 'CST').text = produto_servico.pis_modalidade
                etree.SubElement(pis_item, 'vBC').text = '{:.2f}'.format(produto_servico.pis_valor_base_calculo or 0)
                etree.SubElement(pis_item, 'pPIS').text = '{:.2f}'.format(produto_servico.pis_aliquota_percentual or 0)
                etree.SubElement(pis_item, 'vPIS').text = '{:.2f}'.format(produto_servico.pis_valor or 0)
            elif produto_servico.pis_modalidade == '03':
                pis_item = etree.SubElement(pis, 'PISQtde')
                etree.SubElement(pis_item, 'CST').text = produto_servico.pis_modalidade
                etree.SubElement(pis_item, 'qBCProd').text = '{:.4f}'.format(produto_servico.quantidade_comercial)
                etree.SubElement(pis_item, 'vAliqProd').text = str(produto_servico.pis_aliquota_percentual)
                etree.SubElement(pis_item, 'vPIS').text = '{:.2f}'.format(produto_servico.pis_valor or 0)
            else:
                pis_item = etree.SubElement(pis, 'PISOutr')
                etree.SubElement(pis_item, 'CST').text = produto_servico.pis_modalidade
                if produto_servico.pis_aliquota_percentual and Decimal(produto_servico.pis_aliquota_percentual) != Decimal('0.00'):
                    etree.SubElement(pis_item, 'vBC').text = '{:.2f}'.format(produto_servico.pis_valor_base_calculo or 0)
                    etree.SubElement(pis_item, 'pPIS').text = '{:.2f}'.format(produto_servico.pis_aliquota_percentual or 0)
                else:
                    etree.SubElement(pis_item, 'qBCProd').text = '{:.4f}'.format(produto_servico.quantidade_comercial)
                    etree.SubElement(pis_item, 'vAliqProd').text = str(produto_servico.pis_aliquota_percentual)
                    
                etree.SubElement(pis_item, 'vPIS').text = '{:.2f}'.format(produto_servico.pis_valor or 0)

                ## PISST
                # pis_item = etree.SubElement(pis, 'PISST')
                # etree.SubElement(pis_item, 'vBC').text = produto_servico.pis_valor_base_calculo
                # etree.SubElement(pis_item, 'pPIS').text = produto_servico.pis_aliquota_percentual
                # etree.SubElement(pis_item, 'qBCProd').text = produto_servico.quantidade_comercial
                # etree.SubElement(pis_item, 'vAliqProd').text = produto_servico.pis_aliquota_percentual
                # etree.SubElement(pis_item, 'vPIS').text = produto_servico.pis_valor_base_calculo

            cofinsnt = ('04','05','06','07','08','09')
            ## COFINS
            cofins = etree.SubElement(imposto, 'COFINS')
            if produto_servico.cofins_modalidade in cofinsnt:
                cofins_item = etree.SubElement(cofins, 'COFINSNT')
                etree.SubElement(cofins_item, 'CST').text = produto_servico.cofins_modalidade
            elif produto_servico.cofins_modalidade == '01' or produto_servico.cofins_modalidade == '02':
                cofins_item = etree.SubElement(cofins, 'COFINSAliq')
                etree.SubElement(cofins_item, 'CST').text = produto_servico.cofins_modalidade
                etree.SubElement(cofins_item, 'vBC').text = '{:.2f}'.format(produto_servico.cofins_valor_base_calculo or 0)
                etree.SubElement(cofins_item, 'pCOFINS').text = '{:.2f}'.format(produto_servico.cofins_aliquota_percentual or 0)
                etree.SubElement(cofins_item, 'vCOFINS').text = '{:.2f}'.format(produto_servico.cofins_valor)
            elif produto_servico.cofins_modalidade == '03':
                cofins_item = etree.SubElement(cofins, 'COFINSQtde')
                etree.SubElement(cofins_item, 'CST').text = produto_servico.cofins_modalidade
                etree.SubElement(cofins_item, 'qBCProd').text = '{:.4f}'.format(produto_servico.quantidade_comercial)
                etree.SubElement(cofins_item, 'vAliqProd').text = '{:.4f}'.format(produto_servico.cofins_aliquota_percentual)
                etree.SubElement(cofins_item, 'vCOFINS').text = '{:.2f}'.format(produto_servico.cofins_valor)
            else:
                cofins_item = etree.SubElement(cofins, 'COFINSOutr')
                etree.SubElement(cofins_item, 'CST').text = produto_servico.cofins_modalidade
                if produto_servico.cofins_aliquota_percentual and Decimal(produto_servico.cofins_aliquota_percentual) != Decimal('0.00'):
                    etree.SubElement(cofins_item, 'vBC').text = '{:.2f}'.format(produto_servico.cofins_valor_base_calculo or 0)
                    etree.SubElement(cofins_item, 'pCOFINS').text = '{:.2f}'.format(produto_servico.cofins_aliquota_percentual or 0)
                else:
                    etree.SubElement(cofins_item, 'qBCProd').text = '{:.2f}'.format(produto_servico.quantidade_comercial)
                    etree.SubElement(cofins_item, 'vAliqProd').text = '{:.2f}'.format(produto_servico.cofins_aliquota_percentual)
                etree.SubElement(cofins_item, 'vCOFINS').text = '{:.2f}'.format(produto_servico.cofins_valor or 0)

                ## COFINSST
                # cofins_item = etree.SubElement(cofins, 'COFINSOutr')
                # etree.SubElement(cofins_item, 'vBC').text = produto_servico.cofins_valor_base_calculo
                # etree.SubElement(cofins_item, 'pCOFINS').text = produto_servico.cofins_aliquota_percentual
                # etree.SubElement(cofins_item, 'qBCProd').text = produto_servico.quantidade_comercial
                # etree.SubElement(cofins_item, 'vAliqProd').text = produto_servico.cofins_aliquota_percentual
                # etree.SubElement(cofins_item, 'vCOFINS').text = produto_servico.cofins_valor

            # ICMSUFDest
            if produto_servico.icms_ufdest:
                icms_item = etree.SubElement(imposto, 'ICMSUFDest')
                etree.SubElement(icms_item, 'vBCUFDest').text = '{:.2f}'.format(produto_servico.icms_ufdest["bc_uf_dest"] or 0) #Valor da BC do ICMS na UF de destino
                if "bc_fcp_uf_dest" in produto_servico.icms_ufdest:
                    etree.SubElement(icms_item, 'vBCFCPUFDest').text = '{:.2f}'.format(produto_servico.icms_ufdest["bc_fcp_uf_dest"] or 0) #Valor da BC FCP na UF de destino 
                etree.SubElement(icms_item, 'pFCPUFDest').text = '{:.4f}'.format(produto_servico.icms_ufdest["fcp_percentual_uf_dest"] or 0) #Percentual do ICMS relativo ao Fundo de Combate à Pobreza (FCP) na UF de destino
                etree.SubElement(icms_item, 'pICMSUFDest').text = '{:.4f}'.format(produto_servico.icms_ufdest["icms_percentual_uf_dest"] or 0) #Alíquota interna da UF de destino 
                etree.SubElement(icms_item, 'pICMSInter').text = '{:.2f}'.format(produto_servico.icms_ufdest["icms_inter"] or 0) #Alíquota interestadual das UF envolvidas
                etree.SubElement(icms_item, 'pICMSInterPart').text = '{:.4f}'.format(produto_servico.icms_ufdest["icms_inter_part"] or 0) #Percentual provisório de partilha do ICMS Interestadual 
                if "fcp_uf_dest" in produto_servico.icms_ufdest:
                    etree.SubElement(icms_item, 'vFCPUFDest').text = '{:.2f}'.format(produto_servico.icms_ufdest["fcp_uf_dest"] or 0) #Valor do ICMS relativo ao Fundo de Combate à Pobreza (FCP) da UF de destino
                etree.SubElement(icms_item, 'vICMSUFDest').text = '{:.2f}'.format(produto_servico.icms_ufdest["icms_uf_dest"] or 0) #Valor do ICMS Interestadual para a UF de destino
                etree.SubElement(icms_item, 'vICMSUFRemet').text = '{:.2f}'.format(produto_servico.icms_ufdest["icms_uf_remet"] or 0) #Valor do ICMS Interestadual para a UF do remetente

        # tag impostoDevol
        if produto_servico.ipi_valor_ipi_dev or produto_servico.icms_modalidade in ['70']:
            impostodevol = etree.SubElement(raiz, 'impostoDevol')
            etree.SubElement(impostodevol, 'pDevol').text = '{:.2f}'.format(produto_servico.pdevol or 100)
            ipidev = etree.SubElement(impostodevol, 'IPI')
            etree.SubElement(ipidev, 'vIPIDevol').text = '{:.2f}'.format(produto_servico.ipi_valor_ipi_dev or 0)

        # informacoes adicionais do produto 
        if produto_servico.informacoes_adicionais:
            etree.SubElement(raiz, 'infAdProd').text = produto_servico.informacoes_adicionais

        if retorna_string:
            return etree.tostring(raiz, encoding="unicode", pretty_print=True)
        else:
            return raiz

    def _serializar_responsavel_tecnico(self, responsavel_tecnico, tag_raiz='infRespTec', retorna_string=True):
        raiz = etree.Element(tag_raiz)
        etree.SubElement(raiz, 'CNPJ').text = responsavel_tecnico.cnpj
        etree.SubElement(raiz, 'xContato').text = responsavel_tecnico.contato
        etree.SubElement(raiz, 'email').text = responsavel_tecnico.email
        etree.SubElement(raiz, 'fone').text = responsavel_tecnico.fone

        if retorna_string:
            return etree.tostring(raiz, encoding="unicode", pretty_print=True)
        else:
            return raiz

    def _serializar_nota_fiscal(self, nota_fiscal, tag_raiz='infNFe', retorna_string=True):
        raiz = etree.Element(tag_raiz, versao=self._versao)

        # 'Id' da tag raiz
        # Ex.: NFe35080599999090910270550010000000011518005123
        raiz.attrib['Id'] = nota_fiscal.identificador_unico

        if six.PY2:
            from dateutil.tz import tzlocal
            tz = datetime.now(tzlocal()).strftime("%z")
        else:
            tz = datetime.now().astimezone().strftime('%z')
        tz = "{}:{}".format(tz[:-2], tz[-2:])

        # Dados da Nota Fiscal
        ide = etree.SubElement(raiz, 'ide')
        etree.SubElement(ide, 'cUF').text = CODIGOS_ESTADOS[nota_fiscal.uf]
        etree.SubElement(ide, 'cNF').text = nota_fiscal.codigo_numerico_aleatorio
        etree.SubElement(ide, 'natOp').text = nota_fiscal.natureza_operacao
        etree.SubElement(ide, 'mod').text = str(nota_fiscal.modelo)
        etree.SubElement(ide, 'serie').text = nota_fiscal.serie
        etree.SubElement(ide, 'nNF').text = str(nota_fiscal.numero_nf)
        etree.SubElement(ide, 'dhEmi').text = nota_fiscal.data_emissao.strftime('%Y-%m-%dT%H:%M:%S') + tz

        if nota_fiscal.modelo == 55 and nota_fiscal.data_saida_entrada:
            etree.SubElement(ide, 'dhSaiEnt').text = nota_fiscal.data_saida_entrada.strftime('%Y-%m-%dT%H:%M:%S') + tz
        
        """dhCont Data e Hora da entrada em contingência E B01 D 0-1 Formato AAAA-MM-DDThh:mm:ssTZD (UTC - Universal
            Coordinated Time)
            Exemplo: no formato UTC para os campos de Data-Hora, "TZD" pode ser -02:00 (Fernando de Noronha), -03:00 (Brasília) ou -04:00 (Manaus), no
            horário de verão serão -01:00, -02:00 e -03:00. Exemplo: "2010-08-19T13:00:15-03:00".
        """
        etree.SubElement(ide, 'tpNF').text = str(nota_fiscal.tipo_documento)  # 0=entrada 1=saida
        """ nfce suporta apenas operação interna
            Identificador de local de destino da operação 1=Operação interna;2=Operação interestadual;3=Operação com exterior.
        """
        if nota_fiscal.modelo == 65:
            etree.SubElement(ide, 'idDest').text = str(1)
        else:
            etree.SubElement(ide, 'idDest').text = str(nota_fiscal.indicador_destino)
        etree.SubElement(ide, 'cMunFG').text = nota_fiscal.municipio
        etree.SubElement(ide, 'tpImp').text = str(nota_fiscal.tipo_impressao_danfe)
        """ ### CONTINGENCIA ###
            1=Emissão normal (não em contingência);
            2=Contingência FS-IA, com impressão do DANFE em formulário de segurança;
            3=Contingência SCAN (Sistema de Contingência do Ambiente Nacional);
            4=Contingência DPEC (Declaração Prévia da Emissão em Contingência);
            5=Contingência FS-DA, com impressão do DANFE em formulário de segurança;
            6=Contingência SVC-AN (SEFAZ Virtual de Contingência do AN);
            7=Contingência SVC-RS (SEFAZ Virtual de Contingência do RS);
            9=Contingência off-line da NFC-e (as demais opções de contingência são válidas também para a NFC-e).
            Para a NFC-e somente estão disponíveis e são válidas as opções de contingência 5 e 9.
        """
        if self._contingencia != None:
            if nota_fiscal.forma_emissao == '1':
                nota_fiscal.forma_emissao = '9'
        etree.SubElement(ide, 'tpEmis').text = str(nota_fiscal.forma_emissao)
        etree.SubElement(ide, 'cDV').text = nota_fiscal.dv_codigo_numerico_aleatorio
        etree.SubElement(ide, 'tpAmb').text = str(self._ambiente)
        etree.SubElement(ide, 'finNFe').text = str(nota_fiscal.finalidade_emissao)
        if nota_fiscal.modelo == 65:
            etree.SubElement(ide, 'indFinal').text = str(1)
            etree.SubElement(ide, 'indPres').text = str(1)
        else:
            etree.SubElement(ide, 'indFinal').text = str(nota_fiscal.cliente_final)
            etree.SubElement(ide, 'indPres').text = str(nota_fiscal.indicador_presencial)
        etree.SubElement(ide, 'procEmi').text = str(nota_fiscal.processo_emissao)
        etree.SubElement(ide, 'verProc').text = '%s %s' % (self._nome_aplicacao, nota_fiscal.versao_processo_emissao)


        ### NF-e referenciada (utilizado em casos de devolução/garantia) ###
        # Apenas NF-e
        if nota_fiscal.modelo == 55:
            if nota_fiscal.notas_fiscais_referenciadas:
                for refNFe in nota_fiscal.notas_fiscais_referenciadas:
                    nfref = etree.SubElement(ide, 'NFref')
                    etree.SubElement(nfref, 'refNFe').text = refNFe.chave_acesso

        ### CONTINGENCIA ###
        if self._contingencia != None:
            etree.SubElement(ide, 'dhCont').text = nota_fiscal.data_emissao.strftime('%Y-%m-%dT%H:%M:%S') + tz # Data e Hora da entrada em contingência AAAA-MM-DDThh:mm:ssTZD
            etree.SubElement(ide, 'xJust').text = nota_fiscal.self._contingencia  # Justificativa da entrada em contingência (min 20, max 256 caracteres)

        # Emitente
        raiz.append(self._serializar_emitente(nota_fiscal.emitente, retorna_string=False))

        # Destinatário
        try:
            raiz.append(self._serializar_cliente(nota_fiscal.cliente, modelo=nota_fiscal.modelo, retorna_string=False))
        except AttributeError as e:
            # NFC-e pode ser gerada sem destinatário
            if nota_fiscal.modelo == 65:
                pass
            else:
                raise e

        # autXML
        if nota_fiscal.modelo == 55:
            try:
                raiz.append(self._serializar_autxml(nota_fiscal,retorna_string=False))
            except:
                pass 

        # Retirada
        if nota_fiscal.retirada:
            raiz.append(self._serializar_entrega_retirada(
                nota_fiscal.retirada,
                retorna_string=False,
                tag_raiz='retirada',
                ))

        # Entrega
        if nota_fiscal.entrega:
            raiz.append(self._serializar_entrega_retirada(
                nota_fiscal.entrega,
                retorna_string=False,
                tag_raiz='entrega',
                ))

        # Itens
        for num, item in enumerate(nota_fiscal.produtos_e_servicos):
            det = self._serializar_produto_servico(item, modelo=nota_fiscal.modelo, retorna_string=False, nota_fiscal=nota_fiscal)
            det.attrib['nItem'] = str(num+1)

            raiz.append(det)

        # Totais
        total = etree.SubElement(raiz, 'total')
        icms_total = etree.SubElement(total, 'ICMSTot')
        etree.SubElement(icms_total, 'vBC').text = '{:.2f}'.format(nota_fiscal.totais_icms_base_calculo)
        etree.SubElement(icms_total, 'vICMS').text = '{:.2f}'.format(nota_fiscal.totais_icms_total)
        etree.SubElement(icms_total, 'vICMSDeson').text = '{:.2f}'.format(nota_fiscal.totais_icms_desonerado)  # Valor Total do ICMS desonerado
        if nota_fiscal.totais_fcp_destino:
            etree.SubElement(icms_total, 'vFCPUFDest').text = '{:.2f}'.format(nota_fiscal.totais_fcp_destino)
        if nota_fiscal.totais_icms_inter_destino:
            etree.SubElement(icms_total, 'vICMSUFDest').text = '{:.2f}'.format(nota_fiscal.totais_icms_inter_destino)
        if nota_fiscal.totais_icms_inter_remetente:
            etree.SubElement(icms_total, 'vICMSUFRemet').text = '{:.2f}'.format(nota_fiscal.totais_icms_remetente)
        etree.SubElement(icms_total, 'vFCP').text = '{:.2f}'.format(nota_fiscal.totais_fcp)
        etree.SubElement(icms_total, 'vBCST').text = '{:.2f}'.format(nota_fiscal.totais_icms_st_base_calculo)
        etree.SubElement(icms_total, 'vST').text = '{:.2f}'.format(nota_fiscal.totais_icms_st_total)
        etree.SubElement(icms_total, 'vFCPST').text = '{:.2f}'.format(nota_fiscal.totais_fcp_st)
        etree.SubElement(icms_total, 'vFCPSTRet').text = '{:.2f}'.format(nota_fiscal.totais_fcp_st_ret)
        etree.SubElement(icms_total, 'vProd').text = '{:.2f}'.format(abs(nota_fiscal.totais_icms_total_produtos_e_servicos))
        etree.SubElement(icms_total, 'vFrete').text = '{:.2f}'.format(nota_fiscal.totais_icms_total_frete)
        etree.SubElement(icms_total, 'vSeg').text = '{:.2f}'.format(nota_fiscal.totais_icms_total_seguro)
        etree.SubElement(icms_total, 'vDesc').text = '{:.2f}'.format(nota_fiscal.totais_icms_total_desconto)

        # Tributos
        etree.SubElement(icms_total, 'vII').text = '{:.2f}'.format(nota_fiscal.totais_icms_total_ii)
        etree.SubElement(icms_total, 'vIPI').text = '{:.2f}'.format(nota_fiscal.totais_icms_total_ipi)
        etree.SubElement(icms_total, 'vIPIDevol').text = '{:.2f}'.format(nota_fiscal.totais_icms_total_ipi_dev)
        etree.SubElement(icms_total, 'vPIS').text = '{:.2f}'.format(nota_fiscal.totais_icms_pis)
        etree.SubElement(icms_total, 'vCOFINS').text = '{:.2f}'.format(nota_fiscal.totais_icms_cofins)

        etree.SubElement(icms_total, 'vOutro').text = '{:.2f}'.format(nota_fiscal.totais_icms_outras_despesas_acessorias)
        etree.SubElement(icms_total, 'vNF').text = '{:.2f}'.format(nota_fiscal.totais_icms_total_nota) 
        if nota_fiscal.totais_tributos_aproximado:
            etree.SubElement(icms_total, 'vTotTrib').text = '{:.2f}'.format(nota_fiscal.totais_tributos_aproximado)

        # ISSQN
        if nota_fiscal.totais_issqn_base_calculo_iss:
            issqn_total = etree.SubElement(total, 'ISSQNtot')
            etree.SubElement(issqn_total, 'vServ').text = '{:.2f}'.format(nota_fiscal.totais_issqn_base_calculo_iss)
            etree.SubElement(issqn_total, 'vBC').text = '{:.2f}'.format(nota_fiscal.totais_issqn_base_calculo_iss)
            if nota_fiscal.totais_issqn_total_iss:
                etree.SubElement(issqn_total, 'vISS').text = '{:.2f}'.format(nota_fiscal.totais_issqn_total_iss)
            if nota_fiscal.totais_issqn_pis:
                etree.SubElement(issqn_total, 'vPIS').text = '{:.2f}'.format(nota_fiscal.totais_issqn_pis)
            if nota_fiscal.totais_issqn_cofins:
                etree.SubElement(issqn_total, 'vCOFINS').text = '{:.2f}'.format(nota_fiscal.totais_issqn_cofins)
            if nota_fiscal.data_competencia_servico:
                etree.SubElement(issqn_total, 'dCompet').text = nota_fiscal.data_competencia_servico.strftime('%Y-%m-%d')
            else:
                etree.SubElement(issqn_total, 'dCompet').text = datetime.now().strftime('%Y-%m-%d')
            
            try:
                if nota_fiscal.issqn_vissret:
                    etree.SubElement(issqn_total, 'vISSRet').text = '{:.2f}'.format(nota_fiscal.issqn_vissret)
                
                if nota_fiscal.issqn_cregtrib:
                    etree.SubElement(issqn_total, 'cRegTrib').text = str(nota_fiscal.issqn_cregtrib)
            except Exception as e:
                print (str(e))

        # Transporte
        transp = etree.SubElement(raiz, 'transp')
        etree.SubElement(transp, 'modFrete').text = str(nota_fiscal.transporte_modalidade_frete)

        # Apenas NF-e
        if nota_fiscal.modelo == 55:
            # Transportadora
            if nota_fiscal.transporte_transportadora:
                transp.append(self._serializar_transportadora(
                    nota_fiscal.transporte_transportadora,
                    retorna_string=False,
                    ))

            # Veículo
            if nota_fiscal.transporte_veiculo_placa and nota_fiscal.transporte_veiculo_uf:
                veiculo = etree.SubElement(transp, 'veicTransp')
                etree.SubElement(veiculo, 'placa').text = nota_fiscal.transporte_veiculo_placa # Obrigatório EX: XXX9999
                etree.SubElement(veiculo, 'UF').text = nota_fiscal.transporte_veiculo_uf
                # Registro Nacional de Transportador de Carga (ANTT)
                if nota_fiscal.transporte_veiculo_rntc:
                    etree.SubElement(veiculo, 'RNTC').text = nota_fiscal.transporte_veiculo_rntc

            # Reboque
            if nota_fiscal.transporte_reboque_placa and nota_fiscal.transporte_reboque_uf:
                reboque = etree.SubElement(transp, 'reboque')
                etree.SubElement(reboque, 'placa').text = nota_fiscal.transporte_reboque_placa
                etree.SubElement(reboque, 'UF').text = nota_fiscal.transporte_reboque_uf
                # Registro Nacional de Transportador de Carga (ANTT)
                if nota_fiscal.transporte_reboque_rntc:
                    etree.SubElement(reboque, 'RNTC').text = nota_fiscal.transporte_reboque_rntc

            # Volumes
            if nota_fiscal.transporte_volumes:
                for volume in nota_fiscal.transporte_volumes:
                    vol = etree.SubElement(transp, 'vol')
                    if volume.quantidade:
                        etree.SubElement(vol, 'qVol').text = str(volume.quantidade)
                        etree.SubElement(vol, 'esp').text = volume.especie
                        if volume.marca:
                            etree.SubElement(vol, 'marca').text = volume.marca
                        if volume.numeracao:
                            etree.SubElement(vol, 'nVol').text = volume.numeracao
                        etree.SubElement(vol, 'pesoL').text = str(volume.peso_liquido)
                        etree.SubElement(vol, 'pesoB').text = str(volume.peso_bruto)

                        # Lacres
                        if volume.lacres:
                            lacres = etree.SubElement(vol, 'lacres')
                            for lacre in volume.lacres:
                                etree.SubElement(lacres, 'nLacre').text = lacre.numero_lacre

        # Faturas/Duplicatas
        if nota_fiscal.fatura_numero and nota_fiscal.fatura_valor_original:
            cobr = etree.SubElement(raiz, 'cobr')
            fat = etree.SubElement(cobr, 'fat')
            etree.SubElement(fat, 'nFat').text = str(nota_fiscal.fatura_numero)
            etree.SubElement(fat, 'vOrig').text = '{:.2f}'.format(nota_fiscal.fatura_valor_original)
            etree.SubElement(fat, 'vDesc').text = '{:.2f}'.format(nota_fiscal.fatura_valor_desconto)
            etree.SubElement(fat, 'vLiq').text = '{:.2f}'.format(nota_fiscal.fatura_valor_liquido)

            if nota_fiscal.duplicatas:
                for d_ in nota_fiscal.duplicatas:
                    dup = etree.SubElement(cobr, 'dup')
                    etree.SubElement(dup, 'nDup').text = str(d_.numero)
                    etree.SubElement(dup, 'dVenc').text = str(d_.data_vencimento.strftime('%Y-%m-%d'))
                    etree.SubElement(dup, 'vDup').text = '{:.2f}'.format(d_.valor)

        # Pagamento
        """ Obrigatório o preenchimento do Grupo Informações de Pagamento para NF-e e NFC-e.
        Para as notas com finalidade de Ajuste ou Devolução o campo Forma de Pagamento deve ser preenchido com 90=Sem Pagamento. """
        pag = etree.SubElement(raiz, 'pag')
        detpag = etree.SubElement(pag, 'detPag')

        if nota_fiscal.indicacao_pagamento:
            etree.SubElement(detpag, 'indPag').text = str(nota_fiscal.indicacao_pagamento)

        if nota_fiscal.finalidade_emissao == '3' or nota_fiscal.finalidade_emissao == '4':
            etree.SubElement(detpag, 'tPag').text = '90'

            if str(nota_fiscal.tipo_pagamento) == '99': # Outros
                try:
                    descricao_pagamento = nota_fiscal.descricao_pagamento or 'Sem Informacao'
                    etree.SubElement(detpag, 'xPag').text = str(descricao_pagamento)[:60]
                except:
                    etree.SubElement(detpag, 'xPag').text = str('Sem Informacao')

            etree.SubElement(detpag, 'vPag').text = '{:.2f}'.format(0)
        else:
            etree.SubElement(detpag, 'tPag').text = str(nota_fiscal.tipo_pagamento).zfill(2)
            
            if str(nota_fiscal.tipo_pagamento) == '99': # Outros
                try:
                    descricao_pagamento = nota_fiscal.descricao_pagamento or 'Sem Informacao'
                    etree.SubElement(detpag, 'xPag').text = str(descricao_pagamento)[:60]
                except:
                    etree.SubElement(detpag, 'xPag').text = str('Sem Informacao')
            
            if str(nota_fiscal.tipo_pagamento).zfill(2) == '90':
                etree.SubElement(detpag, 'vPag').text = '{:.2f}'.format(0)
            else:
                etree.SubElement(detpag, 'vPag').text = '{:.2f}'.format(nota_fiscal.totais_icms_total_nota)
            
            try:                    
                """ Tipo de Integração do processo de pagamento com o sistema de automação da empresa:
                    1=Pagamento integrado com o sistema de automação da empresa (Ex.: equipamento TEF, Comércio Eletrônico);
                    2= Pagamento não integrado com o sistema de automação da empresa (Ex.: equipamento POS);
                """

                if nota_fiscal.cartao_tipo_integracao:
                    cartao = etree.SubElement(detpag, 'card')
                    etree.SubElement(cartao, 'tpIntegra').text = str(nota_fiscal.cartao_tipo_integracao)
                    etree.SubElement(cartao, 'CNPJ').text = str(re.sub('[^0-9]', '', nota_fiscal.cartao_cnpj or '')) # Informar o CNPJ da Credenciadora de cartão de crédito / débito
                    etree.SubElement(cartao, 'tBand').text = str(nota_fiscal.cartao_tipo_bandeira or '') # 01=Visa 02=Mastercard 03=American Express 04=Sorocred 05=Diners Club 06=Elo 07=Hipercard 08=Aura 09=Caba 99=Outros
                    etree.SubElement(cartao, 'cAut').text = str(nota_fiscal.cartao_numero_autorizacao[:20] if nota_fiscal.cartao_numero_autorizacao else '') # Identifica o número da autorização da transação da operação com cartão de crédito e/ou débito

                    if nota_fiscal.cartao_cnpj_receb:
                        etree.SubElement(cartao, 'CNPJReceb').text = str(re.sub('[^0-9]', '', nota_fiscal.cartao_cnpj_receb or '')) # Informar CNPJ Beneficiário do Pagamento (NT2023.004)
                    
                    if nota_fiscal.cartao_terminal_pgto:
                        etree.SubElement(cartao, 'idTermPag').text = str(nota_fiscal.cartao_terminal_pgto[:40] or '') # Informar Identificador do Terminal usado para pagamento (NT2023.004)

                    if nota_fiscal.cartao_valor_troco and nota_fiscal.cartao_valor_troco > Decimal('0.00'):
                        etree.SubElement(cartao, 'vTroco').text = '{:.2f}'.format(nota_fiscal.cartao_valor_troco or 0)
            except Exception as e:
                traceback.print_exc()
                
            # troco
            # etree.SubElement(pag, 'vTroco').text = str('')

        # Intermediador
        try:
            if nota_fiscal.intermed_cnpj:
                if nota_fiscal.modelo == 55:
                    infintermed = etree.SubElement(raiz, 'infIntermed')
                    etree.SubElement(infintermed, 'CNPJ').text = str(nota_fiscal.intermed_cnpj or "")[:14]
                    etree.SubElement(infintermed, 'idCadIntTran').text = str(nota_fiscal.intermed_idcadinttran or "")[:60]
        except:
            traceback.print_exc()

        # Informações adicionais
        if nota_fiscal.informacoes_adicionais_interesse_fisco or nota_fiscal.informacoes_complementares_interesse_contribuinte:
            info_ad = etree.SubElement(raiz, 'infAdic')
            if nota_fiscal.informacoes_adicionais_interesse_fisco:
                etree.SubElement(info_ad, 'infAdFisco').text = nota_fiscal.informacoes_adicionais_interesse_fisco
            if nota_fiscal.informacoes_complementares_interesse_contribuinte:
                etree.SubElement(info_ad, 'infCpl').text = nota_fiscal.informacoes_complementares_interesse_contribuinte

        # Responsavel Tecnico NT2018/003
        if nota_fiscal.responsavel_tecnico:
            raiz.append(self._serializar_responsavel_tecnico(
                nota_fiscal.responsavel_tecnico[0], retorna_string=False))


        if retorna_string:
            return etree.tostring(raiz, encoding="unicode", pretty_print=True)
        else:
            return raiz

    def serializar_evento(self, evento, tag_raiz='evento', retorna_string=False):
        if six.PY2:
            from dateutil.tz import tzlocal
            tz = datetime.now(tzlocal()).strftime("%z")
        else:
            tz = datetime.now().astimezone().strftime('%z')
        tz = "{}:{}".format(tz[:-2], tz[-2:])
        raiz = etree.Element(tag_raiz, versao='1.00', xmlns=NAMESPACE_NFE)
        e = etree.SubElement(raiz, 'infEvento', Id=evento.identificador)
        etree.SubElement(e, 'cOrgao').text = CODIGOS_ESTADOS[evento.uf.upper()]
        etree.SubElement(e, 'tpAmb').text = str(self._ambiente)
        etree.SubElement(e, 'CNPJ').text = evento.cnpj # Empresas somente terão CNPJ
        #etree.SubElement(e, 'CPF').text = ''
        etree.SubElement(e, 'chNFe').text = evento.chave
        etree.SubElement(e, 'dhEvento').text = evento.data_emissao.strftime('%Y-%m-%dT%H:%M:%S') + tz
        etree.SubElement(e, 'tpEvento').text = evento.tp_evento
        etree.SubElement(e, 'nSeqEvento').text = str(evento.n_seq_evento)
        etree.SubElement(e, 'verEvento').text = '1.00'
        det = etree.SubElement(e, 'detEvento', versao='1.00')
        etree.SubElement(det, 'descEvento').text = evento.descricao
        if evento.descricao == 'Cancelamento':
            etree.SubElement(det, 'nProt').text = evento.protocolo
            etree.SubElement(det, 'xJust').text = evento.justificativa
        elif evento.descricao == 'Carta de Correcao':
            etree.SubElement(det, 'xCorrecao').text = re.sub(r'[\t\r\n]','',evento.correcao)
            etree.SubElement(det, 'xCondUso').text = evento.cond_uso
        elif evento.descricao == 'Operacao nao Realizada':
            etree.SubElement(det, 'xJust').text = evento.justificativa

        if retorna_string:
            return etree.tostring(raiz, encoding="unicode", pretty_print=True)
        else:
            return raiz


class SerializacaoQrcode(object):
    """ Classe que gera e serializa o qrcode de NFC-e no xml """
    def gerar_qrcode(self, token, csc, xml, return_qr=False, online=True):
        """ Classe para gerar url do qrcode da NFC-e """
        # Procura atributos no xml
        ns = {'ns':NAMESPACE_NFE}
        sig = {'sig':NAMESPACE_SIG}
        # Tag Raiz NFe Ex: <NFe>
        nfe = xml
        chave = nfe[0].attrib['Id'].replace('NFe','')
        data = nfe.xpath('ns:infNFe/ns:ide/ns:dhEmi/text()', namespaces=ns)[0].encode()
        tpamb = nfe.xpath('ns:infNFe/ns:ide/ns:tpAmb/text()', namespaces=ns)[0]
        cuf = nfe.xpath('ns:infNFe/ns:ide/ns:cUF/text()', namespaces=ns)[0]
        uf = [key for key, value in CODIGOS_ESTADOS.items() if value == cuf][0]

        # tenta encontrar a tag cpf
        try:
            cpf = nfe.xpath('ns:infNFe/ns:dest/ns:CPF/text()', namespaces=ns)[0]
        except IndexError:
            # em caso de erro tenta procurar a tag cnpj
            try:
                cpf = nfe.xpath('ns:infNFe/ns:dest/ns:CNPJ/text()', namespaces=ns)[0]
            except IndexError:
                cpf = None
        total = nfe.xpath('ns:infNFe/ns:total/ns:ICMSTot/ns:vNF/text()', namespaces=ns)[0]
        # icms = nfe.xpath('ns:infNFe/ns:total/ns:ICMSTot/ns:vICMS/text()', namespaces=ns)[0]
        digest = nfe.xpath('sig:Signature/sig:SignedInfo/sig:Reference/sig:DigestValue/text()', namespaces=sig)[0].encode()

        lista_dia = re.findall("-\d{2}", str(data))
        dia = str(lista_dia[1])
        dia = dia[1:]
        replacements = {'0': ''}
        token = re.sub('([0])', lambda m: replacements[m.group()], token)

        #VERSAO_QRCODE =2
        if online:
            #versão online
            url = '{}|{}|{}|{}'.format(chave,VERSAO_QRCODE, tpamb, token)
        else:
            #versão offline
            digest = digest.lower()
            digest = digest.hex()

            url = '{}|{}|{}|{}|{}|{}|{}'.format(
                chave,VERSAO_QRCODE,tpamb,dia,total,digest,token
                )

        url_complementar = url + csc
        url_hash = hashlib.sha1(url_complementar.encode()).digest()
        url_hash = base64.b16encode(url_hash).decode()

        url = 'p={}|{}'.format(url, url_hash)

        # url_chave - Texto com a URL de consulta por chave de acesso a ser impressa no DANFE NFC-e.
        # Informar a URL da “Consulta por chave de acesso da NFC-e”.
        # A mesma URL que deve estar informada no DANFE NFC-e para consulta por chave de acesso
        lista_uf_padrao = ['PR', 'CE', 'RS', 'RJ', 'RO', 'DF']
        if uf.upper() in lista_uf_padrao:
            qrcode = NFCE[uf.upper()]['QR'] + url
            url_chave = NFCE[uf.upper()]['URL']
        elif uf.upper() == 'SP':
            if tpamb == '1':
                qrcode = NFCE[uf.upper()]['HTTPS'] + 'www.' + NFCE[uf.upper()]['QR'] + url
                url_chave = NFCE[uf.upper()]['HTTPS'] + 'www.' + NFCE[uf.upper()]['URL']
            else:
                qrcode = NFCE[uf.upper()]['HTTPS'] + 'www.homologacao.' + NFCE[uf.upper()]['QR'] + url
                url_chave = NFCE[uf.upper()]['HTTPS'] + 'www.homologacao.' + NFCE[uf.upper()]['URL']
        # BA tem comportamento distindo para qrcode e url
        elif uf.upper() == 'BA':
            if tpamb == '1':
                qrcode = NFCE[uf.upper()]['HTTPS'] + NFCE[uf.upper()]['QR'] + url
            else:
                qrcode = NFCE[uf.upper()]['HOMOLOGACAO'] + NFCE[uf.upper()]['QR'] + url
            url_chave = url_chave = NFCE[uf.upper()]['URL']
        # AC, AM, RR, PA,
        else:
            if tpamb == '1':
                qrcode = NFCE[uf.upper()]['HTTPS'] + NFCE[uf.upper()]['QR'] + url
                url_chave = NFCE[uf.upper()]['HTTPS'] + NFCE[uf.upper()]['URL']
            else:
                qrcode = NFCE[uf.upper()]['HOMOLOGACAO'] + NFCE[uf.upper()]['QR'] + url
                url_chave = NFCE[uf.upper()]['HOMOLOGACAO'] + NFCE[uf.upper()]['URL']
        # adicionta tag infNFeSupl com qrcode
        info = etree.Element('infNFeSupl')
        etree.SubElement(info, 'qrCode').text = '<![CDATA['+ qrcode.strip() + ']]>'
        etree.SubElement(info, 'urlChave').text = url_chave
        nfe.insert(1, info)
        # correção da tag qrCode, retira caracteres pois e CDATA
        tnfe = etree.tostring(nfe, encoding='unicode')
        etree.tostring(nfe.find(".//qrCode"), encoding='unicode') \
            .replace('\n','').replace('&lt;','<').replace('&gt;','>').replace('amp;','')
        nfe = etree.fromstring(tnfe)
        # retorna nfe com o qrcode incluido NT2015/002 e qrcode
        if return_qr:
            return nfe, qrcode.strip()
        # retorna apenas nfe com o qrcode incluido NT2015/002
        else:
            return nfe


class SerializacaoNfse(object):
    def __init__(self, autorizador):
        "Recebe uma string com o nome do autorizador."
        self.autorizador = autorizador

    def gerar(self, nfse):
        if self.autorizador.lower() == 'betha':
            from pynfe.processamento.autorizador_nfse import SerializacaoBetha
            return SerializacaoBetha().gerar(nfse)
        else:
            raise Exception('Este método só esta implementado no autorizador Betha.')

    def gerar_lote(self, nfse):
        if self.autorizador.lower() == 'ginfes':
            from pynfe.processamento.autorizador_nfse import SerializacaoGinfes
            return SerializacaoGinfes().serializar_lote_assincrono(nfse)
        else:
            raise Exception('Este método só esta implementado no autorizador ginfes.')

    def consultar_nfse(self, emitente, numero=None, inicio=None, fim=None):
        if self.autorizador.lower() == 'ginfes':
            from pynfe.processamento.autorizador_nfse import SerializacaoGinfes
            return SerializacaoGinfes().consultar_nfse(emitente, numero, inicio, fim)
        else:
            raise Exception('Este método só esta implementado no autorizador ginfes.')

    def consultar_lote(self, emitente, numero):
        if self.autorizador.lower() == 'ginfes':
            from pynfe.processamento.autorizador_nfse import SerializacaoGinfes
            return SerializacaoGinfes().consultar_lote(emitente, numero)
        else:
            raise Exception('Este método só esta implementado no autorizador ginfes.')

    def consultar_rps(self, emitente, numero, serie, tipo):
        if self.autorizador.lower() == 'ginfes':
            from pynfe.processamento.autorizador_nfse import SerializacaoGinfes
            return SerializacaoGinfes().consultar_rps(emitente, numero, serie, tipo)
        else:
            raise Exception('Este método só esta implementado no autorizador ginfes.')

    def consultar_situacao_lote(self, emitente, numero):
        if self.autorizador.lower() == 'ginfes':
            from pynfe.processamento.autorizador_nfse import SerializacaoGinfes
            return SerializacaoGinfes().consultar_situacao_lote(emitente, numero)
        else:
            raise Exception('Este método só esta implementado no autorizador ginfes.')

    def cancelar(self, nfse):
        if self.autorizador.lower() == 'ginfes':
            from pynfe.processamento.autorizador_nfse import SerializacaoGinfes
            ## versao 3
            #return SerializacaoGinfes().cancelar(nfse)
            ## versao 2
            return SerializacaoGinfes().cancelar_v2(nfse)
        elif self.autorizador.lower() == 'betha':
            from pynfe.processamento.autorizador_nfse import SerializacaoBetha
            return SerializacaoBetha().cancelar(nfse)
        else:
            raise Exception('Autorizador não suportado para cancelamento!')
