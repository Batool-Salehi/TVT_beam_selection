import csv
import tensorflow as tf
from tensorflow.keras import metrics
from tensorflow.keras.models import model_from_json,Model
from tensorflow.keras.layers import Dense,concatenate
from tensorflow.keras.losses import categorical_crossentropy
from tensorflow.keras.optimizers import Adadelta,Adam
from sklearn.model_selection import train_test_split
from ModelHandler import ModelHandler
import numpy as np
import argparse
from sklearn.model_selection import KFold
from tqdm import tqdm


def top_10_accuracy(y_true,y_pred):
    return metrics.top_k_categorical_accuracy(y_true,y_pred,k=10)

def top_50_accuracy(y_true,y_pred):
    return metrics.top_k_categorical_accuracy(y_true,y_pred,k=50)

def sub2ind(array_shape, rows, cols):
    ind = rows*array_shape[1] + cols
    ind[ind < 0] = -1
    ind[ind >= array_shape[0]*array_shape[1]] = -1
    return ind

def ind2sub(array_shape, ind):
    ind[ind < 0] = -1
    ind[ind >= array_shape[0]*array_shape[1]] = -1
    rows = (ind.astype('int') / array_shape[1])
    cols = ind % array_shape[1]
    return (rows, cols)



def beamsLogScale(y,thresholdBelowMax):
        # shape is (#,256)
        y_shape = y.shape

        for i in range(0,y_shape[0]):
            thisOutputs = y[i,:]
            logOut = 20*np.log10(thisOutputs + 1e-30)
            minValue = np.amax(logOut) - thresholdBelowMax
            zeroedValueIndices = logOut < minValue
            thisOutputs[zeroedValueIndices]=0
            thisOutputs = thisOutputs / sum(thisOutputs)
            y[i,:] = thisOutputs

        return y

def getBeamOutput(output_file):

    thresholdBelowMax = 6

    print("Reading dataset...", output_file)
    output_cache_file = np.load(output_file)
    yMatrix = output_cache_file['output_classification']

    yMatrix = np.abs(yMatrix)
    yMatrix /= np.max(yMatrix)
    yMatrixShape = yMatrix.shape
    num_classes = yMatrix.shape[1] * yMatrix.shape[2]

    y = yMatrix.reshape(yMatrix.shape[0],num_classes)
    y = beamsLogScale(y,thresholdBelowMax)

    return y,num_classes

def custom_label(output_file):

    print("Reading dataset...", output_file)
    output_cache_file = np.load(output_file)
    yMatrix = output_cache_file['output_classification']

    yMatrix = np.abs(yMatrix)
    yMatrix /= np.max(yMatrix)
    yMatrixShape = yMatrix.shape
    num_classes = yMatrix.shape[1] * yMatrix.shape[2]

    y = yMatrix.reshape(yMatrix.shape[0],num_classes)
    y_shape = y.shape
    for i in range(0,y_shape[0]):
        thisOutputs = y[i,:]
        logOut = 20*np.log10(thisOutputs)
        y[i,:] = logOut

    return y,num_classes


def balance_data(beams,coords):
    Best_beam=[]
    k = 1
    for count,val in enumerate(beams):   # beams is 9..*256
        Index = val.argsort()[-k:][::-1]
        Best_beam.append(Index[0])

    Apperance = {i:Best_beam.count(i) for i in Best_beam}
    Max_apperance = max(Apperance.values())

    for i in tqdm(Apperance.keys()):
        ind = [ind for ind, value in enumerate(Best_beam) if value == i]
        randperm = np.random.permutation(int(Max_apperance-Apperance[i]))

        ADD_beam = np.empty((len(randperm), 256))
        ADD_coord = np.empty((len(randperm), 2))

        for i in range(len(randperm)):
            ADD_beam[i,:] = beams[i]
            ADD_coord[i,:] = coords[i]

        beams = np.concatenate((beams, ADD_beam), axis=0)
        coords = np.concatenate((coords, ADD_coord), axis=0)
    return beams, coords



parser = argparse.ArgumentParser(description='Configure the files before training the net.')
parser.add_argument('data_folder', help='Location of the data directory', type=str)
#TODO: limit the number of input to 3
parser.add_argument('--input', nargs='*', default=['coord'],
choices = ['img', 'coord', 'lidar'],
help='Which data to use as input. Select from: img, lidar or coord.')
parser.add_argument('-p','--plots',
help='Use this parametter if you want to see the accuracy and loss plots',
action='store_true')
args = parser.parse_args()




tf.device('/device:GPU:0')
data_dir = args.data_folder+'/'
tgtRec = 3


if 'coord' in args.input:
    ###############################################################################
    # Coordinate configuration
    #train
    coord_train_input_file = data_dir+'coord_input/coord_train.npz'
    coord_train_cache_file = np.load(coord_train_input_file)
    X_coord_train = coord_train_cache_file['coordinates']
    #validation
    coord_validation_input_file = data_dir+'coord_input/coord_validation.npz'
    coord_validation_cache_file = np.load(coord_validation_input_file)
    X_coord_validation = coord_validation_cache_file['coordinates']

    coord_train_input_shape = X_coord_train.shape

if 'img' in args.input:
    ###############################################################################
    # Image configuration
    resizeFac = 20 # Resize Factor
    nCh = 1 # The number of channels of the image
    imgDim = (360,640) # Image dimensions
    method = 1
    #train
    img_train_input_file = data_dir+'image_input/img_input_train_'+str(resizeFac)+'.npz'
    print("Reading dataset... ",img_train_input_file)
    img_train_cache_file = np.load(img_train_input_file)
    X_img_train = img_train_cache_file['inputs']
    #validation
    img_validation_input_file = data_dir+'image_input/img_input_validation_'+str(resizeFac)+'.npz'
    print("Reading dataset... ",img_validation_input_file)
    img_validation_cache_file = np.load(img_validation_input_file)
    X_img_validation = img_validation_cache_file['inputs']

    img_train_input_shape = X_img_train.shape


if 'lidar' in args.input:
    ###############################################################################
    # LIDAR configuration
    #train
    lidar_train_input_file = data_dir+'lidar_input/lidar_train.npz'
    print("Reading dataset... ",lidar_train_input_file)
    lidar_train_cache_file = np.load(lidar_train_input_file)
    X_lidar_train = lidar_train_cache_file['input']
    #validation
    lidar_validation_input_file = data_dir+'lidar_input/lidar_validation.npz'
    print("Reading dataset... ",lidar_validation_input_file)
    lidar_validation_cache_file = np.load(lidar_validation_input_file)
    X_lidar_validation = lidar_validation_cache_file['input']

    lidar_train_input_shape = X_lidar_train.shape


###############################################################################
# Output configuration
#train
output_train_file = data_dir+'beam_output/beams_output_train.npz'
output_validation_file = data_dir+'beam_output/beams_output_validation.npz'

if args.custom_label:
    y_train,num_classes = custom_label(output_train_file)
    print("check",y_train)
    y_validation, _  = custom_label(output_validation_file)
else:
    y_train,num_classes = getBeamOutput(output_train_file)
    y_validation, _ = getBeamOutput(output_validation_file)



##############################################################################
# Model configuration
##############################################################################

#multimodal
multimodal = False if len(args.input) == 1 else len(args.input)

num_epochs = args.epochs
batch_size = 32
validationFraction = 0.2 #from 0 to 1
modelHand = ModelHandler()
opt = Adam(lr=args.lr)

if 'coord' in args.input:
    print(num_classes)
    print(coord_train_input_shape[1])
    coord_model = modelHand.createArchitecture('coord_mlp',num_classes,coord_train_input_shape[1],'complete')
if 'img' in args.input:
   #num_epochs = 5
    if nCh==1:
        img_model = modelHand.createArchitecture('light_image',num_classes,[img_train_input_shape[1],img_train_input_shape[2],1],'complete')
    else:
        img_model = modelHand.createArchitecture('light_image',num_classes,[img_train_input_shape[1],img_train_input_shape[2],img_train_input_shape[3]],'complete')
if 'lidar' in args.input:
    lidar_model = modelHand.createArchitecture('lidar_marcus',num_classes,[lidar_train_input_shape[1],lidar_train_input_shape[2],lidar_train_input_shape[3]],'complete')


if multimodal == 2:
    if 'coord' in args.input and 'lidar' in args.input:
        combined_model = concatenate([coord_model.output,lidar_model.output])
        z = Dense(num_classes,activation="relu")(combined_model)
        model = Model(inputs=[coord_model.input,lidar_model.input],outputs=z)
        model.compile(loss=categorical_crossentropy,
                    optimizer=opt,
                    metrics=[metrics.categorical_accuracy,
                            metrics.top_k_categorical_accuracy, top_10_accuracy,
                            top_50_accuracy])
        model.summary()
        hist = model.fit([X_coord_train,X_lidar_train],y_train,
        validation_data=([X_coord_validation, X_lidar_validation], y_validation),epochs=num_epochs,batch_size=batch_size)

    elif 'coord' in args.input and 'img' in args.input:
        combined_model = concatenate([coord_model.output,img_model.output])
        z = Dense(num_classes,activation="relu")(combined_model)
        model = Model(inputs=[coord_model.input,img_model.input],outputs=z)
        model.compile(loss=categorical_crossentropy,
                    optimizer=opt,
                    metrics=[metrics.categorical_accuracy,
                            metrics.top_k_categorical_accuracy, top_10_accuracy,
                            top_50_accuracy])
        model.summary()
        hist = model.fit([X_coord_train,X_img_train],y_train,
        validation_data=([X_coord_validation, X_img_validation], y_validation), epochs=num_epochs,batch_size=batch_size)


    else:
        combined_model = concatenate([lidar_model.output,img_model.output])
        z = Dense(num_classes,activation="relu")(combined_model)
        model = Model(inputs=[lidar_model.input,img_model.input],outputs=z)
        model.compile(loss=categorical_crossentropy,
                    optimizer=opt,
                    metrics=[metrics.categorical_accuracy,
                            metrics.top_k_categorical_accuracy, top_10_accuracy,
                            top_50_accuracy])
        model.summary()
        hist = model.fit([X_lidar_train,X_img_train],y_train,
        validation_data=([X_lidar_validation, X_img_validation], y_validation), epochs=num_epochs,batch_size=batch_size)
elif multimodal == 3:
    combined_model = concatenate([lidar_model.output,img_model.output, coord_model.output])
    z = Dense(num_classes,activation="relu")(combined_model)
    model = Model(inputs=[lidar_model.input,img_model.input, coord_model.input],outputs=z)
    model.compile(loss=categorical_crossentropy,
                optimizer=opt,
                metrics=[metrics.categorical_accuracy,
                        metrics.top_k_categorical_accuracy, top_10_accuracy,
                        top_50_accuracy])
    model.summary()
    hist = model.fit([X_lidar_train,X_img_train,X_coord_train],y_train,
            validation_data=([X_lidar_validation, X_img_validation, X_coord_validation], y_validation),
            epochs=num_epochs,batch_size=batch_size)

else:
    if 'coord' in args.input:
        model = coord_model
        model.compile(loss=categorical_crossentropy,
                            optimizer=opt,
                            metrics=[metrics.categorical_accuracy,
                                    metrics.top_k_categorical_accuracy, top_10_accuracy,
                                    top_50_accuracy])
        model.summary()
        hist = model.fit(X_coord_train,y_train,
        validation_data=(X_coord_validation, y_validation),epochs=num_epochs,batch_size=batch_size)

    elif 'img' in args.input:
        model = img_model
        model.compile(loss=categorical_crossentropy,
                    optimizer=opt,
                    metrics=[metrics.categorical_accuracy,
                            metrics.top_k_categorical_accuracy, top_10_accuracy,
                            top_50_accuracy])
        model.summary()
        hist = model.fit(X_img_train,y_train,
        validation_data=(X_img_validation, y_validation),epochs=num_epochs,batch_size=batch_size)

    else:
        model = lidar_model
        model.compile(loss=categorical_crossentropy,
                    optimizer=opt,
                    metrics=[metrics.categorical_accuracy,
                            metrics.top_k_categorical_accuracy, top_10_accuracy,
                            top_50_accuracy])
        model.summary()
        hist = model.fit(X_lidar_train,y_train,
        validation_data=(X_lidar_validation, y_validation),epochs=num_epochs,batch_size=batch_size)





