import logging
from uuid import uuid4

from sourced.ml.extractors import create_extractors_from_args
from sourced.ml.models import OrderedDocumentFrequencies, QuantizationLevels
from sourced.ml.transformers import Ignition, UastExtractor, UastDeserializer, Uast2Quant, \
    BagFeatures2DocFreq, BagFeatures2TermFreq, Uast2BagFeatures, HeadFiles, TFIDF, Cacher, \
    Indexer, Counter, BOWWriter
from sourced.ml.utils import create_engine, EngineConstants


def repos2bow_entry(args):
    log = logging.getLogger("repos2bow")
    engine = create_engine("repos2bow-%s" % uuid4(), **args.__dict__)
    extractors = create_extractors_from_args(args)

    uast_extractor = Ignition(engine, explain=args.explain) \
        .link(HeadFiles()) \
        .link(UastExtractor(languages=args.languages)) \
        .link(Cacher.maybe(args.persist))
    log.info("Extracting UASTs...")
    ndocs = uast_extractor.link(Counter()).execute()
    log.info("Number of documents: %d", ndocs)
    uast_extractor = uast_extractor.link(UastDeserializer())
    quant = Uast2Quant(extractors)
    uast_extractor.link(quant).execute()
    if quant.levels:
        log.info("Writing quantization levels to %s", args.quant)
        QuantizationLevels().construct(quant.levels).save(args.quant)
    uast_extractor = uast_extractor.link(Uast2BagFeatures(
        extractors, EngineConstants.Columns.RepositoryId))
    log.info("Calculating the document frequencies...")
    df = uast_extractor.link(BagFeatures2DocFreq()).execute()
    log.info("Writing docfreq to %s", args.docfreq)
    df_model = OrderedDocumentFrequencies() \
        .construct(ndocs, df) \
        .prune(args.min_docfreq) \
        .greatest(args.vocabulary_size) \
        .save(args.docfreq)
    document_indexer = Indexer(TFIDF.Columns.document)
    uast_extractor \
        .link(BagFeatures2TermFreq()) \
        .link(TFIDF(df_model)) \
        .link(Cacher.maybe(args.persist)) \
        .link(document_indexer) \
        .link(Indexer(TFIDF.Columns.token, df_model.order)) \
        .link(BOWWriter(document_indexer, df_model, args.bow, args.batch)) \
        .execute()