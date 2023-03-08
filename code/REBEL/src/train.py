import omegaconf
import hydra

import pytorch_lightning as pl
from pytorch_lightning.callbacks import EarlyStopping, ModelCheckpoint

from pl_data_modules import BasePLDataModule
from pl_modules import BasePLModule
from transformers import AutoConfig, AutoModelForSeq2SeqLM, AutoTokenizer

from pytorch_lightning.loggers.neptune import NeptuneLogger
from pytorch_lightning.loggers.wandb import WandbLogger

from pytorch_lightning.callbacks import LearningRateMonitor
from generate_samples import GenerateTextSamplesCallback

relations = {'no_relation': 'no relation',
'org:alternate_names': 'alternate name',
'org:city_of_branch': 'city of headquarters',
'org:country_of_branch': 'country of headquarters',
'org:dissolved': 'dissolved',
'org:founded_by': 'founded by',
'org:founded': 'founded',
'org:member_of': 'member of',
'org:members': 'members',
'org:number_of_employees/members': 'number of members',
'org:political/religious_affiliation': 'affiliation',
'org:shareholders': 'shareholders',
'org:stateorprovince_of_branch': 'state of headquarters',
'org:top_members/employees': 'top members',
'org:website': 'website',
'per:age': 'age',
'per:cause_of_death': 'cause of death',
'per:charges': 'charges',
'per:children': 'children',
'per:cities_of_residence': 'city of residence',
'per:city_of_birth': 'place of birth',
'per:city_of_death': 'place of death',
'per:countries_of_residence': 'country of residence',
'per:country_of_birth': 'country of birth',
'per:country_of_death': 'country of death',
'per:date_of_birth': 'date of birth',
'per:date_of_death': 'date of death',
'per:employee_of': 'employee of',
'per:identity': 'identity',
'per:origin': 'origin',
'per:other_family': 'other family',
'per:parents': 'parents',
'per:religion': 'religion',
'per:schools_attended': 'educated at',
'per:siblings': 'siblings',
'per:spouse': 'spouse',
'per:stateorprovince_of_birth': 'state of birth',
'per:stateorprovince_of_death': 'state of death',
'per:stateorprovinces_of_residence': 'state of residence',
'per:title': 'title'}

def train(conf: omegaconf.DictConfig) -> None:
    pl.seed_everything(conf.seed)

    print(omegaconf.OmegaConf.to_yaml(conf))

    config = AutoConfig.from_pretrained(
        conf.config_name if conf.config_name else conf.model_name_or_path,
        decoder_start_token_id = 0,
        early_stopping = False,
        no_repeat_ngram_size = 0,
        dropout=conf.dropout,
    )
    print(config)
    
    tokenizer_kwargs = {
        "use_fast": conf.use_fast_tokenizer,
        "additional_special_tokens": ['<obj>', '<subj>', '<triplet>', '<head>', '</head>', '<tail>', '</tail>'], # Here the tokens for head and tail are legacy and only needed if finetuning over the public REBEL checkpoint, but are not used. If training from scratch, remove this line and uncomment the next one.
#         "additional_special_tokens": ['<obj>', '<subj>', '<triplet>'],
    }

    tokenizer = AutoTokenizer.from_pretrained(
        conf.tokenizer_name if conf.tokenizer_name else conf.model_name_or_path,
        **tokenizer_kwargs
    )

    if conf.dataset_name.split('/')[-1] == 'conll04_typed.py':
        tokenizer.add_tokens(['<peop>', '<org>', '<other>', '<loc>'], special_tokens = True)
    if conf.dataset_name.split('/')[-1] == 'nyt_typed.py':
        tokenizer.add_tokens(['<loc>', '<org>', '<per>'], special_tokens = True)
    if conf.dataset_name.split('/')[-1] == 'docred_typed.py':
        tokenizer.add_tokens(['<actor&director>', '<artist>', '<musician>', '<politician>', '<scholar>', '<writer>', '<athlete>', '<soldier>', '<businessman>', '<monarch>', '<engineer>', '<docter>', '<judge&lawyer>', '<journalist>', '<religious>', '<other_occupations>', '<fictional_character>', '<other_human>', '<continent>', '<country>', '<state&province>', '<city>', '<county_and_town>', '<village>', '<administrative_district>', '<traffic_line>', '<street>', '<other_gpe>', '<body_of_water>', '<island>', '<mountain>', '<other_natural_location>', '<manufacturer>', '<record_label>', '<transport_company>', '<broadcasting_company>', '<publisher>', '<other_company>', '<musical_group>', '<political_party>', '<sports_league>', '<sports_team>', '<research_institution>', '<government_agency>', '<army>', '<religious_organization>', '<international_organization>', '<terrorist_organization>', '<family>', '<other_organization>', '<game>', '<series>', '<magazine>', '<newspaper>', '<software>', '<hardware>', '<brand>', '<plane>', '<car>', '<ship>', '<food>', '<other_product>', '<film>', '<musical_work>', '<television_work>', '<written_work>', '<drama>', '<painting>', '<style>', '<other_art>', '<military_operation>', '<sports_event>', '<contest>', '<play>', '<movement>', '<ceremony_or_festival>', '<other_event>', '<school>', '<community>', '<theatre>', '<station>', '<park>', '<bridge>', '<airport>', '<museum>', '<church>', '<cemetery>', '<hospital>', '<sports_venues>', '<square>', '<bank>', '<dam>', '<palace>', '<exchange>', '<base>', '<other_building>', '<position>', '<species>', '<language>', '<ethnicity>', '<award>', '<record_chart>', '<religion>', '<website>', '<law&policy>', '<academic_discipline>', '<television_network>', '<disease>', '<chemical_and_biological>', '<political_ideology>', '<treaty>', '<concept>', '<natural_phenomenon>', '<method>', '<other_misc>', '<sports_season>', '<period>', '<time>', '<number>'], special_tokens = True)

    model = AutoModelForSeq2SeqLM.from_pretrained(
        conf.model_name_or_path,
        config=config,
    )
    # model = AutoModelForSeq2SeqLM.from_pretrained(
    #     conf.model_name_or_path,
    # )
    # if not conf.finetune:
    model.resize_token_embeddings(len(tokenizer))

    # data module declaration
    pl_data_module = BasePLDataModule(conf, tokenizer, model)

    # main module declaration
    pl_module = BasePLModule(conf, config, tokenizer, model)
    # pl_module = pl_module.load_from_checkpoint(checkpoint_path = conf.checkpoint_path, config = config, tokenizer = tokenizer, model = model)

    wandb_logger = WandbLogger(project = conf.dataset_name.split('/')[-1].replace('.py', ''), name = conf.model_name_or_path.split('/')[-1])

    callbacks_store = []

    if conf.apply_early_stopping:
        callbacks_store.append(
            EarlyStopping(
                monitor=conf.monitor_var,
                mode=conf.monitor_var_mode,
                patience=conf.patience
            )
        )

    callbacks_store.append(
        ModelCheckpoint(
            monitor=conf.monitor_var,
            # monitor=None,
            dirpath=f'experiments/{conf.model_name}',
            save_top_k=conf.save_top_k,
            verbose=True,
            save_last=True,
            mode=conf.monitor_var_mode
        )
    )
    callbacks_store.append(GenerateTextSamplesCallback(conf.samples_interval))
    callbacks_store.append(LearningRateMonitor(logging_interval='step'))
    # trainer
    trainer = pl.Trainer(
        gpus=conf.gpus,
        accumulate_grad_batches=conf.gradient_acc_steps,
        gradient_clip_val=conf.gradient_clip_value,
        val_check_interval=conf.val_check_interval,
        callbacks=callbacks_store,
        max_steps=conf.max_steps,
        # max_steps=total_steps,
        precision=conf.precision,
        amp_level=conf.amp_level,
        logger=wandb_logger,
        resume_from_checkpoint=conf.checkpoint_path,
        limit_val_batches=conf.val_percent_check
    )

    # module fit
    trainer.fit(pl_module, datamodule=pl_data_module)

@hydra.main(config_path='../conf', config_name='root')
def main(conf: omegaconf.DictConfig):
    train(conf)


if __name__ == '__main__':
    main()
